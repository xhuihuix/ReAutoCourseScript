import asyncio
import random

from playwright.async_api import Browser, async_playwright

from config.config_loader import UserData, get_config, read_user_info
from user.user_async import UserAsync
from utils.logger_manager import get_module_logger

class MainAsync:

    def __init__(self):
        self.config = get_config()
        self.module_logger = get_module_logger("Main")
        self.users = []
        self.browser = None

        self.initialized_users = []

    async def run(self):
        batch_size = self.config.project.user_batch_size
        users_data = read_user_info(self.config.account)

        try:
            async with async_playwright() as p:
                browser = await p.firefox.launch(
                    headless=False,
                )
                # 分批处理用户
                total_users = len(users_data)
                self.module_logger.info(f"总共 {total_users} 个用户，每批处理 {batch_size} 个用户")

                for i in range(0, total_users, batch_size):
                    # 获取当前批次的用户
                    current_batch = users_data[i:i + batch_size]
                    batch_number = (i // batch_size) + 1
                    self.module_logger.info(f"处理第 {batch_number} 批用户 ({len(current_batch)} 个用户)")

                    # 处理当前批次
                    initialized_users, results = await self.process_user_batch(
                        current_batch, browser, self.config.cookie.save_path
                    )

                    print(f"第 {batch_number} 批用户处理完成")

                    # 确保当前批次的所有用户会话都被关闭
                    await self.close_all_users(initialized_users)

                    # 如果不是最后一批，添加延迟
                    if i + batch_size < total_users:
                        print("等待一段时间后继续下一批用户...")
                        await asyncio.sleep(5)  # 可根据需要调整延迟时间

                success = True

        except Exception as e:
            print(f"程序执行过程中发生异常: {e}")
        finally:
            # 确保资源被正确释放
            try:
                # 关闭浏览器
                if browser:
                    await browser.close()
                print("所有资源已释放")
            except Exception as cleanup_error:
                print(f"资源清理过程中发生错误: {cleanup_error}")

            # 程序执行完毕后等待用户回车
            if success:
                print("\n程序执行完成，按回车键退出...")
            else:
                print("\n程序执行出现错误，按回车键退出...")
            input()


    async def initialize_user(self, user_data: UserData, browser: Browser, cookie_path: str = None):
        """
            初始化用户
            :param user_data: 用户数据
            :param browser: 浏览器对象
            :param cookie_path: cookie所在文件夹
            :return:
            """
        login_file = f"{cookie_path}_{user_data.username}.json"
        user_async = UserAsync(user_data, browser, login_file)

        try:
            # 只进行初始化（登录）
            await user_async.initialize()
            if user_async.is_initialized():
                self.module_logger.info(f"用户 {user_data.user_name}_{user_data.username} 登录成功")
                return user_async
            else:
                self.module_logger.info(f"用户 {user_data.user_name}_{user_data.username} 登录失败")
                await user_async.close()
                return None
        except Exception as e:
            self.module_logger.error(f"用户 {user_data.user_name}_{user_data.username} 登录出错: {e}")
            await user_async.close()
            return None

    async def run_user_task(self, user_async: UserAsync):
        """
        运行已登录用户的学习任务（可并行执行）
        """
        try:
            self.module_logger.info(f"用户 {user_async.user_data.user_name}_{user_async.user_data.username} 开始执行学习任务")
            await user_async.run()
            self.module_logger.info(f"用户 {user_async.user_data.user_name}_{user_async.user_data.username} 学习任务完成")
            return True
        except Exception as e:
            self.module_logger.error(f"用户 {user_async.user_data.user_name}_{user_async.user_data.username} 执行学习任务出错")
            return False
        finally:
            # 确保用户会话被正确关闭
            try:
                await user_async.close()
                self.module_logger.info(f"用户 {user_async.user_data.user_name}_{user_async.user_data.username} 会话已关闭")
            except Exception as close_error:
                self.module_logger.error(f"用户 {user_async.user_data.user_name}_{user_async.user_data.username} 关闭会话出错")

    async def close_all_users(self, user_list: list[UserAsync]):
        """
        关闭所有用户会话
        """
        for user in user_list:
            if user:
                try:
                    await user.close()
                    self.module_logger.info(f"用户 {user.user_data.user_name}_{user.user_data.username} 会话已关闭")
                except Exception as e:
                    self.module_logger.error(f"用户 {user.user_data.user_name}_{user.user_data.username} 关闭会话出错")

    async def process_user_batch(self, user_batch, browser, cookie_path):
        """
            处理一批用户：登录并执行学习任务
            """
        # 第一阶段：串行登录所有用户
        self.module_logger.info("开始串行登录用户批次...")
        initialized_users = []

        for user_data in user_batch:
            user = await self.initialize_user(user_data, browser, cookie_path)
            if user:
                initialized_users.append(user)
            # 登录间隔延迟
            await asyncio.sleep(random.random() * 3 + 1)

        # 第二阶段：并行执行学习任务
        results = []
        if initialized_users:
            self.module_logger.info("开始并行执行学习任务...")
            tasks = []
            for user in initialized_users:
                task = asyncio.create_task(self.run_user_task(user))
                tasks.append(task)
                # 任务启动间隔延迟
                await asyncio.sleep(random.random() * 5)

            # 等待所有学习任务完成
            results = await asyncio.gather(*tasks, return_exceptions=True)

        return initialized_users, results

if __name__ == "__main__":
    main_async = MainAsync()
    asyncio.run(main_async.run())