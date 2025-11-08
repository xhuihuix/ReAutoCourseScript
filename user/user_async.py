from playwright.async_api import Browser

from config.config_loader import get_config, UserData
from user.login_manager import LoginManager
from user.study_manager import StudyManager
from utils.logger_manager import get_user_module_logger


class UserAsync:
    # 属性

    # 方法
    def __init__(self, user_data: UserData, browser: Browser, login_file: str = None):
        self.config = get_config()
        self.user_data = user_data
        self.browser = browser
        self.login_file = login_file
        self.module_logger = get_user_module_logger(
            f"{self.user_data.user_name}_{self.user_data.username}",
            "Login"
        )

        # 初始化各个模块
        self.login_manager = LoginManager(self.user_data, self.browser, self.login_file)
        self.study_manager = StudyManager(self.user_data)

    async def initialize(self):
        """
        检查用户是否已初始化
        """
        if await self.login_manager.login():
            self.module_logger.info("用户已登录")

    async def close(self):
        """
        释放登录相关资源
        :return:
        """
        await self.login_manager.close()

    async def run(self):  # 调用study_manager.run_study_process()
        """
        运行用户任务
        :return:
        """
        if not self.login_manager.isLogin:
            await self.initialize()
        await self.study_manager.init_context(self.login_manager.context)
        await self.study_manager.run_study_process()

    def is_initialized(self) -> bool:
        """
        检查用户是否已初始化
        :return:
        """
        return self.login_manager.isLogin
