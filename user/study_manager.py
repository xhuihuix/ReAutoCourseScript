import asyncio
import random

from playwright.async_api import BrowserContext, Page, Locator

from config.config_loader import UserData, get_config
from user.course_manager import CourseManager
from utils.logger_manager import get_user_module_logger


class StudyManager:

    def __init__(self, user_data: UserData):
        self.config = get_config()
        self.user_data = user_data
        self.context : BrowserContext | None = None     # 在使用时才会初始化
        self.module_logger = get_user_module_logger(
            f"{self.user_data.user_name}_{self.user_data.username}",
            "Study"
        )

        self.course_manager = CourseManager(self.user_data)

    async def init_context(self, context: BrowserContext):
        self.context = context
        await self.course_manager.init_context(self.context)

    # 方法
    async def run_study_process(self):
        await asyncio.sleep(random.random() * 2 + 1)

        if not self.context:
            self.module_logger.error("用户上下文未初始化")
            return

        self.module_logger.info("开始检查设置状态")
        # 查看未完成课程信息
        if await self.check_is_need_settings():
            self.module_logger.info("需要认证，停止学习任务")
            return

        if not await self.get_project_class_id():
            self.module_logger.info("获取项目课程ID失败")
            return
        await self.course_manager.run_study_course()

    async def check_is_need_settings(self):
        """查看是否需要认证，如果需要认证，则无法进行"""
        response = await self.context.request.post(self.config.web.check_is_need_setting)
        if response.status == 200:
            data = await response.json()
            page = data.get("page", [])
            items = page.get("items", [])
            if len(items) > 0:
                if items[0]["success"] == '1':
                    self.module_logger.info("该用户未认证，停止操作")
                    return True
        return False

    async def get_project_class_id(self) -> bool:
        """获取项目页第一个项目的id"""
        params = {
            "data": "info",
            "page.curPage": 1,
            "page.pageSize": 100,
            "page.searchItem.type": 0,
            "page.searchItem.searchScoreTypeSort": "sort2025",
            "page.searchItem.typeId": 4
        }
        response = await self.context.request.get(
            self.config.web.project_class_id_url,
            params=params
        )
        if response.status == 200:
            project_data = await response.json()
            if project_data.get("errorCode", '') == "0" and project_data.get("errorMessage", "") == "成功":
                page = project_data.get("page", {})
                items = page.get("items", [])
                class_id = items[0].get("id", self.config.video_play.class_id)
                self.user_data.class_id = class_id
                # self.config.video_play.class_id = class_id
                return True
            self.module_logger.error("获取项目id失败")
        return False
