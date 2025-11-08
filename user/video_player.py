import asyncio
import random

from playwright.async_api import BrowserContext, Locator

from config.config_loader import UserData, get_config
from utils.logger_manager import get_user_module_logger


class VideoPlayer:

    # 常量
    ENSURE_MAX_TRY = 4      # 确保视频开始播放的最大尝试次数
    RECOVER_MAX_TRY = 3     # 恢复视频播放失败最大尝试次数
    VIDEO_MAX_RETRY = 3     # 视频学习失败重试次数

    CHECK_FREQ_S = 5        # 视频检查频率(秒)
    REPORT_FREQ_S = 600     # 汇报频率(秒)
    MAX_STUCK_CHECKS = 3    # 最大停顿次数检查次数, 超过该次数认为停顿

    def __init__(self, user_data: UserData):
        self.config = get_config()
        self.user_data = user_data
        self.context: BrowserContext | None = None  # 在使用时才会初始化
        self.module_logger = get_user_module_logger(
            f"{self.user_data.user_name}_{self.user_data.username}",
            "Video"
        )
        self.video_end_requests_flag = False

    async def init_context(self, context: BrowserContext):
        self.context = context
        await self.context.route("**/*", self.block_resources)

    # 方法
    async def play_video_content_with_retry(self, video_frame, content_node):
        """
        带重试机制的视频学习函数

        Args:
            video_frame: 视频框架定位器
            content_node: 内容节点
        """
        retry_count = 0

        while retry_count < self.VIDEO_MAX_RETRY:
            try:
                await self.play_video_content(video_frame, content_node)
                return  # 成功执行，退出重试循环
            except Exception as e:
                retry_count += 1
                self.module_logger.error(f"      → 视频学习第 {retry_count} 次尝试失败: {str(e)}")
                if retry_count < self.VIDEO_MAX_RETRY:
                    self.module_logger.info("      → 尝试刷新页面并重新开始视频学习流程")

                    try:
                        # 刷新页面
                        page = video_frame.page
                        await page.reload()
                        await asyncio.sleep(random.random() * 5 + 1)

                        frame_element = await page.wait_for_selector("#learnHelperIframe", state="visible",
                                                                         timeout=30000)
                        await asyncio.sleep(random.random() * 3 + 1)
                        frame = await  frame_element.content_frame()
                        await frame.click("a[onclick='closeLearnHelper()']")

                        # 重新获取框架定位器
                        section_frame = page.frame_locator("#mainCont")
                        video_frame = section_frame.frame_locator("#mainFrame")

                        # 重新点击内容节点
                        await content_node.evaluate("""element => {
                                element.scrollIntoView({block: 'center'});
                                element.click();
                            }""")
                        await asyncio.sleep(random.random() * 3 + 1)

                    except Exception as refresh_error:
                        self.module_logger.error(f"      → 刷新页面失败: {str(refresh_error)}")
                else:
                    self.module_logger.error("      → 达到最大重试次数，视频学习失败")

    async def play_video_content(self, video_frame, content_node):
        """
        学习视频内容

        Args:
            video_frame: 视频框架定位器
            content_node: 内容节点
        """
        self.module_logger.info(f"      → 开始播放视频")

        try:
            # 定位div.jwmute元素
            jwmute_div = video_frame.locator("span.jwmute")

            # 检查div.jwmute是否存在
            try:
                # 检查div.jwmute是否也报告jwtoggle类
                jwmute_classes = await jwmute_div.get_attribute("class")
                if jwmute_classes and "jwtoggle" in jwmute_classes:
                    self.module_logger.info("      → div.jwmute已包含jwtoggle类，无需点击按钮")
                else:
                    # 如果div.jwmute存在但不包含jwtoggle类，则通过JavaScript点击其下的button
                    mute_button = jwmute_div.locator("button")
                    # 使用JavaScript直接触发点击事件
                    await mute_button.evaluate("button => button.click()")
                    self.module_logger.info("      → 已通过JavaScript点击静音按钮")
            except Exception:
                self.module_logger.info("      → 未找到div.jwmute元素，跳过静音操作")

            await asyncio.sleep(random.random() * 2 + 1)
            # 确保视频开始播放
            await self.ensure_video_playing(video_frame)

            # 获取视频总时长
            total_video_time_str = await video_frame.locator(
                "#container_controlbar_duration").text_content()
            total_video_time_s = self.time_str_to_seconds(total_video_time_str)

            self.module_logger.info(f"      → 视频总时长: {total_video_time_str}")
            # 监控视频播放进度
            await self.monitor_video_progress(video_frame, total_video_time_s, content_node)

        except Exception as e:
            self.module_logger.error(f"      → 处理视频内容时发生错误: {str(e)}")
            # 重新抛出异常以触发重试机制
            raise e

    async def ensure_video_playing(self, video_frame):
        """
        确保视频开始播放
        """
        cur_try = 0
        # 等待播放按钮出现
        try:
            await video_frame.locator("#container_display_button").wait_for(state="visible", timeout=15000)
        except Exception as e:
            self.module_logger.error(f"等待播放按钮超时: {e}")

        # 循环尝试播放直到播放器加载完成
        while cur_try <= self.ENSURE_MAX_TRY:
            # 检查是否已经播放(通过是否存在暂停按钮jwtoggle判断)
            jwtoggle_count = await video_frame.locator(".jwtoggle").count()
            if jwtoggle_count > 0:
                self.module_logger.info("视频已在播放中")
                break

            self.module_logger.info("尝试启动视频播放")
            try:
                await video_frame.locator("#container_display_button").click()
            except Exception as e:
                self.module_logger.error(f"点击播放按钮失败: {e}")

            cur_try += 1
            await asyncio.sleep(random.random() * 2 + 1)  # 增加等待时间防止误判

        if cur_try > self.ENSURE_MAX_TRY:
            self.module_logger.info("达到最大尝试次数，视频可能未正常播放")

    async def monitor_video_progress(self, video_frame, total_video_time_s, content_node: Locator):
        """
        监控视频播放进度并处理卡顿等问题
        """

        # 卡顿检测配置
        stuck_check_count = 0

        # 初始化状态变量
        last_report_time = 0
        last_video_time_s = -1  # 初始值设为-1以便第一次比较
        start_time = asyncio.get_event_loop().time()
        self.video_end_requests_flag = False

        while True:
            try:
                elapsed_time = asyncio.get_event_loop().time() - start_time

                # 检查内容项是否已完成（通过完成标志检测）
                if self.video_end_requests_flag:
                    self.module_logger.info("视频已结束，等待内容项完成")
                    break

                try:
                    complete_flag = await content_node.locator("span.flagover-icon").count()
                    if complete_flag >= 1:
                        self.module_logger.info("检测到内容已完成标志，视频播放结束")
                        break
                except Exception as e:
                    self.module_logger.error(f"检查完成标志时出错: {e}")

                try:
                    # 获取当前播放时间
                    cur_video_time_str = (await video_frame.locator("#container_controlbar_elapsed").text_content()).strip()
                    cur_video_time_s = self.time_str_to_seconds(cur_video_time_str)
                except Exception as e:
                    self.module_logger.error(f"获取当前播放时间失败: {e}")
                    await asyncio.sleep(self.CHECK_FREQ_S)
                    continue

                # 检查视频是否卡住（包括播放按钮显示播放状态但进度条不动的情况）
                if cur_video_time_s == last_video_time_s and cur_video_time_s >= 0:
                    stuck_check_count += 1
                    self.module_logger.info(
                        f"检测到播放时间未变化: {cur_video_time_str} ({stuck_check_count}/{self.MAX_STUCK_CHECKS})")

                    if stuck_check_count >= self.MAX_STUCK_CHECKS:
                        self.module_logger.info("检测到视频播放卡住，尝试重新播放")
                        await self.try_recover_playback(video_frame)
                        stuck_check_count = 0  # 重置计数器
                else:
                    # 如果播放时间有变化，重置卡顿计数器
                    if last_video_time_s != -1:  # 排除初始状态
                        stuck_check_count = 0

                # 更新上次播放时间
                last_video_time_s = cur_video_time_s

                # 定期报告播放进度
                if elapsed_time - last_report_time >= self.REPORT_FREQ_S:
                    progress = cur_video_time_s / total_video_time_s * 100
                    self.module_logger.info(
                        f"视频播放情况 {cur_video_time_str}/{self.seconds_to_time_str(total_video_time_s)}, 进度: {progress:.2f}%")
                    last_report_time = elapsed_time

                await  asyncio.sleep(self.CHECK_FREQ_S)

            except Exception as e:
                self.module_logger.error(f"视频播放监控出错: {e}")
                raise e

    async def try_recover_playback(self, video_frame):
        """
        尝试恢复视频播放
        """
        attempt = 0

        self.module_logger.info("尝试恢复视频播放")

        try:
            while attempt < self.RECOVER_MAX_TRY:
                # 检查当前是否已经在播放（通过是否存在暂停按钮jwtoggle判断）
                # jwtoggle_count = await video_frame.locator(".jwtoggle").count()

                # 即使有jwtoggle按钮，也要尝试点击播放按钮来确保播放状态
                self.module_logger.info(f"尝试点击播放按钮 (第{attempt + 1}次)")
                try:
                    await video_frame.locator("#container_display_button").click()
                    # 等待一小段时间让播放状态更新
                    await asyncio.sleep(0.5)

                    # 检查是否开始播放
                    jwtoggle_count = await video_frame.locator(".jwtoggle").count()
                    if jwtoggle_count > 0:
                        self.module_logger.info("成功恢复视频播放")
                        return True

                except Exception as click_error:
                    self.module_logger.error(f"点击播放按钮失败: {click_error}")

                attempt += 1

            # 如果点击播放按钮无效，尝试刷新页面
            self.module_logger.info("点击播放按钮无效，尝试刷新页面")
            try:
                # 获取包含视频的页面对象
                page = video_frame.page
                # 刷新页面
                await page.reload()
                # 等待页面加载完成
                await asyncio.sleep(5)

                # 重新获取frame对象
                section_frame = page.frame_locator("#mainCont")
                if section_frame:
                    video_frame = section_frame.frame_locator("#mainFrame")
                    if video_frame:
                        # 尝试点击播放按钮
                        try:
                            await video_frame.locator("#container_display_button").click()
                            await asyncio.sleep(1)
                            jwtoggle_count = await video_frame.locator(".jwtoggle").count()
                            if jwtoggle_count > 0:
                                self.module_logger.info("刷新页面后点击播放按钮成功")
                                return True
                        except Exception as click_error:
                            self.module_logger.error(f"刷新后点击播放按钮失败: {click_error}")
            except Exception as reload_error:
                self.module_logger.error(f"刷新页面失败: {reload_error}")

            self.module_logger.error("达到最大尝试次数，未能恢复视频播放")
            return False

        except Exception as e:
            self.module_logger.error(f"恢复视频播放过程中发生异常: {e}")
            return False

    async def block_resources(self, route):
        url = route.request.url

        # 阻止特定的视频CDN域名或路径模式
        video_patterns = [
            "learningTime_endVideoLearning.action"
        ]

        if any(pattern in url for pattern in video_patterns):
            self.video_end_requests_flag = True
            await route.continue_()
        # 阻止其他不需要的资源类型
        elif route.request.resource_type in ["image", "media", "font", "video"]:
            await route.abort()
        else:
            await route.continue_()

    @staticmethod
    def time_str_to_seconds(time_str):
        """将时间字符串转换为秒，支持XX、XX:XX、XX:XX:XX格式"""
        # 统一中文冒号为英文冒号
        time_str = time_str.replace("：", ":").strip()

        # 按冒号分割时间部分
        time_parts = time_str.split(":")

        # 根据不同格式处理
        if len(time_parts) == 1:  # XX格式(秒)
            return int(time_parts[0])
        elif len(time_parts) == 2:  # XX:XX格式(分钟:秒)
            minutes, seconds = map(int, time_parts)
            return minutes * 60 + seconds
        elif len(time_parts) == 3:  # XX:XX:XX格式(小时:分钟:秒)
            hours, minutes, seconds = map(int, time_parts)
            return hours * 3600 + minutes * 60 + seconds
        else:
            raise ValueError(f"不支持的时间格式: {time_str}")

    @staticmethod
    def seconds_to_time_str(seconds):
        """将秒数转换为时间字符串格式 (XX:XX:XX)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
