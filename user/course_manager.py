import asyncio
import random

from playwright.async_api import BrowserContext, Page, Locator

from config.config_loader import UserData, get_config
from user.video_player import VideoPlayer
from utils.logger_manager import get_user_module_logger


class CourseManager:


    def __init__(self, user_data: UserData):
        self.config = get_config()
        self.user_data = user_data
        self.context : BrowserContext | None = None     # 在使用时才会初始化
        self.module_logger = get_user_module_logger(
            f"{self.user_data.user_name}_{self.user_data.username}",
            "Course"
        )

        self.video_player = VideoPlayer(user_data)

    def init_context(self, context: BrowserContext):
        self.context = context
        self.video_player.init_context(self.context)

    async def run_study_course(self):
        unfinished_course = await self.get_unfinished_courses()
        self.module_logger.info(f"共找到 {len(unfinished_course)} 个未完成课程")
        for index, course in enumerate(unfinished_course):
            self.module_logger.info(f"开始学习第 {index + 1}/{len(unfinished_course)} 个课程: {course.get('name')}")
            page_obj = await self.context.new_page()
            try:
                self.module_logger.info(f"正在学习第{index + 1}个课程, 课程名称为:{course.get('name')}")
                await asyncio.sleep(random.random() * 3  + 1)
                await self.study_single_course(course, page_obj)
            finally:
                await page_obj.close()

        self.module_logger.info(f"用户 {self.user_data.user_name}_{self.user_data.username} 所有课程学习任务完成")

    async def study_single_course(self, course, page_obj: Page):
        """
        学习单个课程, 首先进行选课,然后打开对应页面学习
        """
        payload = {
            "entity.openCourse": course.get("openCourseId", ""),
            "entity.projectId": ""
        }

        save_response = await self.context.request.get(
            self.config.web.select_elective_url,
            params=payload
        )

        if save_response.status == 200:
            save_data = await save_response.json()
            page = save_data.get('page', {})
            items = page.get('items', [])

            if items and len(items) > 0:
                message = items[0].get('message', {})
                success = message.get('success', '0')

                if success == '1':
                    await self.open_and_study_course(course, page_obj)
                else:
                    self.module_logger.error(f"进入课程空间失败: {message.get('info', '未知错误')}")
            else:
                self.module_logger.error("保存选课信息失败: 返回数据格式不正确")
        else:
            self.module_logger.error(f"保存课程信息请求失败, 状态码: {save_response.status}")

    async def open_and_study_course(self, course, page_obj: Page):
        """
        打开视频页面并学习课程
        """
        course_url = f"{course['learnspaceUrl']}/learnspace/sign/signLearn.action"
        course_url += f"?template=blue&courseId={course['id']}"
        course_url += f"&loginType=true&loginId={self.user_data.username}&sign=0&siteCode={self.config.web.site_code}"
        course_url += "&domain=youxun.webtrn.cn"

        await page_obj.goto(course_url)

        if await page_obj.title() == "课程未发布":
            self.module_logger.error("课程未发布, 请检查该用户能否选择该课程!!!")
            return

        frame_element = await page_obj.wait_for_selector("#learnHelperIframe", state="visible", timeout=30000)
        await asyncio.sleep(random.random() * 3 + 1)
        frame = await  frame_element.content_frame()
        await frame.click("a[onclick='closeLearnHelper()']")
        self.module_logger.info("已经关闭帮助助手页面")
        await self.study_course_content(page_obj)

    async def study_course_content(self, page_obj: Page):
        """
        根据课程详情进行学习
        优化后的版本，只对需要学习的内容添加延迟，提高已完成课程的检查速度
        """
        course_study_detail = await self.parse_course_structure(page_obj)
        # 初始化页面框架定位器
        section_frame = page_obj.frame_locator("#mainCont")
        video_frame = section_frame.frame_locator("#mainFrame")

        # 遍历所有章节，筛选出需要学习的内容
        chapters_to_learn = []

        for chapter_index, chapter in enumerate(course_study_detail[:]):
            chapter_title = chapter.get('title', '未知章节')

            # 获取章节下的所有小节
            sections = chapter.get('sections', [])
            sections_to_learn = []

            for section_index, section in enumerate(sections):
                section_title = section.get('title', '未知小节')

                # 获取小节下的所有内容项
                contents = section.get('contents', [])
                contents_to_learn = []

                # 筛选出未完成的内容
                for content in contents:
                    is_completed = content.get('completestate', '0')
                    if is_completed != '1':
                        contents_to_learn.append(content)

                # 只有当小节中有未完成内容时才添加到待学习列表
                if contents_to_learn:
                    sections_to_learn.append({
                        'section': section,
                        'contents_to_learn': contents_to_learn
                    })

            # 只有当章节中有未完成内容时才添加到待学习列表
            if sections_to_learn:
                chapters_to_learn.append({
                    'chapter': chapter,
                    'sections_to_learn': sections_to_learn
                })

        # 输出统计信息
        total_contents_count = 0
        for chapter_info in chapters_to_learn:
            for section_info in chapter_info['sections_to_learn']:
                total_contents_count += len(section_info['contents_to_learn'])

        self.module_logger.info(f"开始学习课程，共 {len(chapters_to_learn)} 个章节需要学习，{total_contents_count} 个内容需要完成")

        if total_contents_count > 0:
            await self.show_course_structure(page_obj)

        await asyncio.sleep(random.random() * 3 + 1)

        # 遍历需要学习的章节进行学习
        for chapter_index, chapter_info in enumerate(chapters_to_learn):
            chapter = chapter_info['chapter']
            chapter_title = chapter.get('title', '未知章节')
            sections_to_learn = chapter_info['sections_to_learn']

            self.module_logger.info(f"▶▶ 开始学习第 {chapter_index + 1}/{len(chapters_to_learn)} 章节: {chapter_title}")

            # 遍历章节下的需要学习的小节
            for section_index, section_info in enumerate(sections_to_learn):
                section = section_info['section']
                contents_to_learn = section_info['contents_to_learn']
                section_title = section.get('title', '未知小节')

                self.module_logger.info(f"  ▶ 开始学习第 {section_index + 1}/{len(sections_to_learn)} 小节: {section_title}")

                # 遍历小节下的需要学习的内容项
                for content_index, content in enumerate(contents_to_learn):
                    content_title = content.get('title', '未知内容')
                    content_type = content.get('itemtype', 'unknown')

                    self.module_logger.info(f"    [{content_index + 1}/{len(contents_to_learn)}] {content_title} [{content_type}]")
                    self.module_logger.info(f"      → 开始学习内容")

                    await self.study_single_content(content, video_frame)

                    # 内容间添加延迟（仅在需要学习的内容之间添加）
                    if content_index < len(contents_to_learn) - 1:  # 不是最后一条内容才添加延迟
                        await asyncio.sleep(random.random() * 3 + 1)

                # 小节间添加延迟（仅在需要学习的小节之间添加）
                if section_index < len(sections_to_learn) - 1:  # 不是最后一个小节才添加延迟
                    await asyncio.sleep(random.random() * 3 + 1)

            # 章节间添加延迟（仅在需要学习的章节之间添加）
            if chapter_index < len(chapters_to_learn) - 1:  # 不是最后一个章节才添加延迟
                await asyncio.sleep(random.random() * 5 + 1)

        self.module_logger.info("课程学习完成")

    async def study_single_content(self, content: dict, video_frame):
        """
        学习单个内容项

        Args:
            content: 内容项信息字典
            video_frame: 视频框架定位器
        """
        content_title = content.get('title', '未知内容')
        content_type = content.get('itemtype', 'unknown')
        clicked = False
        try:
            await asyncio.sleep(random.random() * 3 + 1)
            try:
                await content['node'].evaluate("""element => {
                element.scrollIntoView({block: 'center'});
                element.click();
                }""")
                clicked = True
                self.module_logger.info(f"      → 点击 {content_title}")
            except Exception as e:
                 self.module_logger.error(f"      → 点击 {content_title} 失败：{e}")

            await asyncio.sleep(1)
            if content_type.strip() == 'video':
                await self.video_player.play_video_content_with_retry(video_frame, content['node'])
            elif content_type.strip() == 'doc':
                await self.study_document_content()
            elif content_type.strip() == 'test':
                await self.start_exam_content()
            else:
                self.module_logger.info(f"      → 内容类型 {content_type}，暂不支持")
                await asyncio.sleep(random.random() * 3 + 1)
        except Exception as e:
            self.module_logger.error(f"      → 尝试学习 {content_title} 失败：{e}")

    async def parse_course_structure(self, page_obj: Page):
        """
        解析课程目录结构并返回结构化数据（只读操作）

        Returns:
            list: 包含章节、小节和内容项的嵌套结构列表
        """
        section_frame = page_obj.frame_locator("#mainCont")
        learn_list_obj = section_frame.locator("#learnMenu")

        # 遍历learn_list_obj的子div节点
        course_structure = []
        child_nodes: Locator = learn_list_obj.locator("> div")
        chapter_count = await child_nodes.count()

        chapter_index = 1
        i = 0

        while i < chapter_count:
            chapter_element = child_nodes.nth(i)

            # 检查是否为章节节点
            if await chapter_element.get_attribute("class") == "s_chapter":
                chapter_title = await chapter_element.get_attribute("title")
                self.module_logger.info(f"解析章节 {chapter_index}: {chapter_title}")

                # 获取下一节点作为小节列表容器
                section_list_obj = child_nodes.nth(i + 1)
                section_list_child_nodes = section_list_obj.locator("> div")
                section_count = await section_list_child_nodes.count()

                sections = []
                section_index = 1
                j = 0

                while j < section_count:
                    section_element = section_list_child_nodes.nth(j)

                    # 检查是否为小节节点
                    if await section_element.get_attribute("class") == "s_section":
                        section_title = await section_element.get_attribute("title")
                        self.module_logger.info(f"  解析小节 {chapter_index}.{section_index}: {section_title}")

                        # 获取下一节点作为内容项列表容器
                        section_wrap_obj = section_list_child_nodes.nth(j + 1)
                        content_items = section_wrap_obj.locator("> div")
                        content_count = await content_items.count()

                        contents = []
                        content_index = 1

                        # 遍历所有内容项
                        for k in range(content_count):
                            content_element = content_items.nth(k)
                            content_title = await content_element.get_attribute("title")
                            item_type = await content_element.get_attribute("itemtype")
                            complete_state = await content_element.get_attribute("completestate")

                            content_detail = {
                                "node": content_element,
                                "title": content_title,
                                "itemtype": item_type,
                                "completestate": complete_state,
                            }

                            contents.append(content_detail)
                            self.module_logger.info(
                                f"    解析内容项 {chapter_index}.{section_index}.{content_index}: [{item_type}] {content_title} [{'已完成学习' if complete_state == '1' else '未完成学习'}]")
                            content_index += 1

                        section_detail = {
                            "title": section_title,
                            "contents": contents
                        }
                        sections.append(section_detail)
                        section_index += 1

                    j += 2

                chapter_detail = {
                    "title": chapter_title,
                    "sections": sections
                }
                course_structure.append(chapter_detail)
                chapter_index += 1

                # 跳过下一个节点，因为它是章节的内容容器，已经被处理
                i += 1

            i += 1
        return course_structure

    async def get_learn_course(self, search_key: str = "") -> list:
        """获取课程信息"""
        params = {
            "data": ["course", "detail"],
            "page.curPage": 1,
            "page.pageSize": self.config.video_play.each_batch,
            "page.searchItem.classId": self.config.video_play.class_id,
            "page.searchItem.status": 0,
            "page.searchItem.labelName": "",
            "page.searchItem.labelCode": "",
            "page.searchItem.searchKey": search_key,
            "page.orderBy": 1
        }
        response = await self.context.request.get(
            self.config.web.course_status_url,
            params=params
        )
        if response.status == 200:
            course_data = await response.json()
            page = course_data.get('page', {})
            items = page.get('items', [])
            await asyncio.sleep(random.random() * 2)

            return items

        return []

    async def get_unfinished_courses(self) -> list:
        """获取当前用户未完成课程"""
        accumulate_credit = 0
        learn_credit = 0
        have_learn_course = []
        unfinished_courses = []

        # 首先查询必修课程状态
        if not self.user_data.must_learn_course == "None":
            for must_course_name in self.user_data.must_learn_course:
                await asyncio.sleep(random.random() * 2 + 2)
                course_items = await self.get_learn_course(must_course_name)
                if not course_items:
                    self.module_logger.info(f"未找到必修课程 {must_course_name}, 请确认课程名称是否正确")
                    continue

                # 默认获取第一个课程
                course_item = course_items[0]

                name = course_item.get('name')
                percent = course_item.get('percent')
                credit = course_item.get('credit')
                course_id = course_item.get('id')

                # 检查是否已添加到相应列表中
                is_in_unfinished = any(i['id'] == course_id for i in unfinished_courses)
                is_in_learned = any(i['id'] == course_id for i in have_learn_course)

                if not percent or not credit:
                    continue

                if int(percent) >= 100:
                    if is_in_learned:
                        continue
                    have_learn_course.append(course_item)
                    accumulate_credit += int(credit)
                    self.module_logger.info(f"必修课程: {name} 已完成, 学分: {credit}")
                elif int(percent) < 100:
                    if is_in_unfinished:
                        continue
                    learn_credit += int(credit)
                    unfinished_courses.append(course_item)
                    self.module_logger.info(f"必修课程: {name} 未完成, 学分{credit}")


        must_course_learn_credit = learn_credit
        total_earned_credit = accumulate_credit + learn_credit
        remaining_credit_needed = self.user_data.need_credit - total_earned_credit

        self.module_logger.info(f"总计学分{self.user_data.need_credit}, 必修课共: {total_earned_credit} 学分, 还需额外学: {remaining_credit_needed} 学分")

        # 如果必修课学分已满足要求，则直接返回
        if total_earned_credit >= self.user_data.need_credit:
            self.module_logger.info("已达到目标学分要求， 无需学习更多课程")
            return unfinished_courses

        # 获取所有课程补充最低学分要求
        all_courses = await self.get_learn_course()

        #　先统计已完成的非必修课程学分
        for course in all_courses:
            name = course.get('name')
            percent = course.get('percent')
            credit = course.get('credit')
            course_id = course.get('id')

            if not percent or not credit or int(percent) < 100:
                continue

            if any(i['id'] == course_id for i in have_learn_course):
                continue

            have_learn_course.append(course)
            accumulate_credit += int(credit)
            self.module_logger.info(f"非必修课程: {name} 已完成, 学分: {credit}")

        # 如果学分仍不足，选择未完成的非必修课程
        if accumulate_credit + learn_credit < self.user_data.need_credit:
            extra_credit = 0
            for course in all_courses:
                name = course.get('name')
                percent = course.get('percent')
                credit = course.get('credit')
                course_id = course.get('id')

                # 只选择未完成且能帮助达到学分要求的课程
                if (percent and credit and int(percent) < 100 and
                        accumulate_credit + learn_credit < self.user_data.need_credit and
                        not any(i['id'] == course_id for i in unfinished_courses)):

                    unfinished_courses.append(course)
                    extra_credit += int(credit)
                    learn_credit += int(credit)

                    # 如果已经满足学分要求，就停止添加课程
                    if accumulate_credit + learn_credit >= self.user_data.need_credit:
                        break

            self.module_logger.info(
                f"还需要 {remaining_credit_needed} 学分，找到 {len(unfinished_courses)} 个未完成课程，预计可获得学分: {extra_credit}"
            )
        else:
            self.module_logger.info(f"已达到目标学分 {self.user_data.need_credit}, 累计获得学分: {accumulate_credit}")
            self.module_logger.info(f"必修课程需要学习: {must_course_learn_credit}")

        return unfinished_courses

    async def study_document_content(self):
        """
        学习文档内容
        """
        self.module_logger.info(f"      → 文档内容，无需特殊处理")
        await asyncio.sleep(random.random() * 3 + 2)

    async def start_exam_content(self):
        """
        学习文档内容
        """
        self.module_logger.info(f"      → 文档内容，无需特殊处理")
        await asyncio.sleep(random.random() * 3 + 2)

    @staticmethod
    async def show_course_structure(page_obj: Page):
        """
        显示课程结构中的隐藏元素，确保所有章节和小节可见

        Args:
            page_obj: 页面对象
        """
        await asyncio.sleep(random.random() * 3 + 1)
        secton_frame = page_obj.frame_locator("#mainCont")
        learn_list_obj = secton_frame.locator("#learnMenu")

        # 遍历所有learn_list_obj的子div节点
        child_nodes = learn_list_obj.locator("> div")
        chapter_count = await child_nodes.count()
        i = 0
        while i < chapter_count:
            chapter_element = child_nodes.nth(i)
            # 检查是否为章节节点
            if await chapter_element.get_attribute("class") == "s_chapter":
                # 获取下一节点作为小节列表容器
                section_list_obj = child_nodes.nth(i + 1)
                # 显示小节列表
                await section_list_obj.evaluate("(element) => element.style.display = 'block'")
                section_list_child_nodes = section_list_obj.locator("> div")
                section_count = await section_list_child_nodes.count()

                j = 0
                while j < section_count:
                    section_element = section_list_child_nodes.nth(j)

                    # 检查是否为小节节点
                    if await section_element.get_attribute("class") == "s_section":
                        # 获取下一节点作为内容项列表容器
                        section_wrap_obj = section_list_child_nodes.nth(j + 1)
                        # 显示内容项列表
                        await section_wrap_obj.evaluate("(element) => element.style.display = 'block'")

                    j += 2

                # 跳过下一个节点，因为它是章节的内容容器，已经被处理
                i += 1

            i += 1

    async def select_elective_course(self, course) -> bool:
        pass