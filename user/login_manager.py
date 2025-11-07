import asyncio
import base64
import json
import os.path
import random

import aiohttp
from aiohttp import ClientSession, ClientError
from playwright.async_api import Browser, BrowserContext

from config.config_loader import UserData, get_config
from utils.captcha import recognize_captcha_async
from utils.logger_manager import get_user_module_logger


class LoginManager:

    # 常量
    MAX_LOGIN_ATTEMPTS = 3

    def __init__(self, user_data: UserData, browser: Browser, login_file: str = None):
        self.config = get_config()
        self.user_data = user_data
        self.browser = browser
        self.login_file = login_file
        self.isLogin = False
        self.session: ClientSession | None = None  # 声明类型并初始化为None
        self.context: BrowserContext | None = None  # 声明类型并初始化为None
        self.module_logger = get_user_module_logger(
            f"{self.user_data.user_name}_{self.user_data.username}",
            "Login"
        )

    async def login(self):
        """
        异步初始化用户: 首先尝试缓存登录, 如果登录失败才会正常登录流程
        """
        if os.path.exists(self.login_file):
            self.context = await self.browser.new_context(storage_state=self.login_file)
            await self.context.route("**/*", self.block_resources)
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined  // 覆盖为undefined
                });
            """)
            await self.context.set_extra_http_headers({"Accept-Language": "zh-CN"})
            if await self.verify_login():
                self.isLogin = True
                self.module_logger.info("登录验证成功")
                await asyncio.sleep(2)
                return  True
            else:
                self.module_logger.info(f"用户 {self.user_data.user_name}_{self.user_data.username} 缓存登录验证失败，尝试重新登录")
                if await self.try_login():
                    self.isLogin = True
                    self.module_logger.info("登录验证成功")
                    await asyncio.sleep(2)
                    return  True
                else:
                    self.module_logger.error("登录验证失败")
                    return False
        else:
            self.module_logger.info(f"用户 {self.user_data.user_name}_{self.user_data.username} 无缓存，开始登录")
            self.session = ClientSession()
            if await self.try_login():
                self.isLogin = True
                self.module_logger.info("登录成功")
                await asyncio.sleep(2)
                return  True
            else:
                self.module_logger.error("登录失败")
                return False

    # 方法
    async def try_login(self) -> bool:
        """异步登录功能"""
        # 创建aiohttp客户端会话
        if not hasattr(self, 'session') or self.session is None:
            self.session = ClientSession()

        self.session.headers.update(self.get_headers())

        cur_login_attempts = 0
        base_delay = 1  # 基础延迟时间

        while cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
            cur_login_attempts += 1
            try:
                # 计算指数退避延迟
                delay = base_delay * (2 ** (cur_login_attempts - 1)) + random.random() * 2
                self.module_logger.info(f"第 {cur_login_attempts} 次登录尝试，等待 {delay:.2f} 秒后执行")

                # 首先访问登录页面，更新cookie参数
                response = await self.session.get(self.config.web.login_page_url)
                if response.status != 200:
                    self.module_logger.error(f"访问登录页面失败，状态码: {response.status}")
                    if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                        self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        self.module_logger.error("达到最大重试次数，登录页面访问失败")
                        return False

                await asyncio.sleep(random.random() * 2 + 1)

                # 获取验证码和识别结果
                auth_code = ''
                try:
                    captcha_response = await self.session.get(self.config.web.qr_code_url)
                    if captcha_response.status == 200:
                        # 获取验证码图片
                        captcha_content = await captcha_response.read()
                        auth_code_base64 = base64.b64encode(captcha_content).decode("utf-8")
                        auth_code = await recognize_captcha_async(
                            self.config.qr_code.api_url,
                            self.config.qr_code.token,
                            auth_code_base64
                        )
                        self.module_logger.info(f"验证码识别结果: {auth_code}")
                    else:
                        self.module_logger.warning(f"获取验证码失败，状态码: {captcha_response.status}")
                        if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                            await asyncio.sleep(delay)
                            continue
                        else:
                            return False
                except ClientError as e:
                    self.module_logger.error(f"网络请求验证码时发生错误: {str(e)}")
                    if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                        self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise

                # 构造登录请求参数
                request_param = {
                    "LoginID": self.user_data.username,
                    "Password": self.user_data.userpwd,
                    "AuthCode": auth_code,
                    "ContentType": 'json',
                    "client_id": self.config.web.client_id,
                    "response_type": "code",
                    "scope": "user_info",
                    "AppID": "11",
                    "redirect_uri": self.config.web.redirect_url + self.config.web.login_page_url
                }

                data_json = json.dumps(request_param)
                data_b64 = base64.b64encode(data_json.encode("utf-8")).decode("utf-8")

                # 构造最终的请求数据
                payload = {
                    "data": data_b64,
                    "ContentType": "json"
                }

                response = await self.session.post(
                    self.config.web.sso_login_url,
                    data=payload,
                )

                if response.status != 200:
                    self.module_logger.error(f"登录请求失败，状态码 {response.status}")
                    if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                        self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        self.module_logger.error("达到最大重试次数，登录请求失败")
                        return False

                # 检查响应的内容类型
                try:
                    content_type = response.headers.get('content-type', '').lower()

                    if 'application/json' in content_type:
                        result = await response.json()
                    elif 'text/javascript' in content_type:
                        text_content = await response.text()
                        result = json.loads(text_content)
                    else:
                        text_content = await response.text()
                        result = json.loads(text_content)
                except Exception as e:
                    self.module_logger.error(f"解析登录响应JSON失败: {str(e)}")
                    self.module_logger.error(f"响应内容: {await response.text()}")
                    if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                        self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise

                if not result.get("success"):
                    error_message = result.get("message", "未知错误")
                    self.module_logger.error(f"登录失败，错误信息: {error_message}")

                    # 如果是验证码错误，重新获取验证码重试
                    if "验证码" in error_message or "authcode" in error_message.lower():
                        self.module_logger.error(
                            f"第 {cur_login_attempts} 次尝试失败, 因验证码失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    # 如果是账号密码错误，直接返回失败，不需要重试
                    elif "密码" in error_message or "password" in error_message.lower():
                        self.module_logger.error("账号或密码错误，终止重试")
                        return False
                    # 其他错误根据剩余尝试次数决定是否重试
                    elif cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                        self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        return False

                # 处理重定向，更新cookie参数
                redirect_url = result.get("redirectURL") or result.get("RedirectURL")
                if not redirect_url:
                    self.module_logger.error(f"登录失败，未找到重定向URL")
                    if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                        self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        self.module_logger.error("达到最大重试次数，未找到重定向URL")
                        return False

                try:
                    redirect_response = await self.session.get(redirect_url)
                    if redirect_response.status != 200:
                        self.module_logger.error(f"重定向请求失败，状态码 {redirect_response.status}")
                        if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                            self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            self.module_logger.error("达到最大重试次数，重定向请求失败")
                            return False
                except ClientError as e:
                    self.module_logger.error(f"重定向请求时发生网络错误: {str(e)}")
                    if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                        self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise

                self.module_logger.info(f"登录成功")
                # 转换 session cookies 到 context 并保存
                return await self.convert_session_to_context()

            except ClientError as e:
                self.module_logger.error(f"网络请求时发生错误: {str(e)}")
                if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                    self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise
            except Exception as e:
                self.module_logger.error(f"登录过程中发生未预期的错误: {str(e)}")
                if cur_login_attempts < self.MAX_LOGIN_ATTEMPTS:
                    self.module_logger.error(f"第 {cur_login_attempts} 次尝试失败，{delay:.2f} 秒后重新尝试...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise

        self.module_logger.error(f"达到最大登录尝试次数 ({self.MAX_LOGIN_ATTEMPTS})，登录失败")
        return False

    async def verify_login(self) -> bool:
        """验证登陆状态"""
        params = {
            "data": "info",
            "page.curPage": 1,
            "page.pageSize": 10,
            "page.searchItem.type": 0
        }

        if self.context:
            response = await self.context.request.get(
                self.config.web.check_login_status_url,
                params=params
            )
            if response.status == 200:
                result = await response.json()
                if result.get('errorCode') == '0' and result.get('errorMessage') == '成功':
                    items = result.get('page', {}).get('items', [])
                    if items and items[0].get('info', {}).get('loginId'):
                        return True
                else:
                    self.module_logger.error(f"登录状态验证失败，错误信息: {result.get('message', '未知错误')}")
            else:
                self.module_logger.error(f"登录状态验证请求失败，状态码 {response.status}")
        return False

    async def convert_session_to_context(self) -> bool:
        """
        将 aiohttp session 中的 cookies 转换为 Playwright context 并保存到文件
        """
        # 创建新的context
        self.context = await self.browser.new_context()
        await self.context.route("**/*", self.block_resources)
        # 注入JS代码，隐藏webdriver标识
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined  // 覆盖为undefined
            });
        """)

        if hasattr(self.session, 'cookie_jar'):
            cookies = []
            for cookie in self.session.cookie_jar:
                secure = cookie["secure"] if "secure" in cookie else False
                http_only = cookie["httponly"] if "httponly" in cookie else False

                cookies.append({
                    "name": cookie.key,
                    "value": cookie.value,
                    "domain": cookie["domain"] if "domain" in cookie else cookie.key,
                    "path": cookie["path"] if "path" in cookie else "/",
                    "secure": bool(secure),
                    "httpOnly": bool(http_only)
                })

            if cookies:
                await self.context.add_cookies(cookies)

        if await self.verify_login():
            if self.login_file:
                folder_path = os.path.dirname(self.login_file)
                if folder_path and not os.path.exists(folder_path):
                    os.makedirs(folder_path)

                await self.context.storage_state(path=self.login_file)
                self.module_logger.info(f"已保存登录信息到 {self.login_file}")
            return True
        else:
            self.module_logger.error(f"无法验证登录状态")
            return False


    async def close(self):
        """
        清理资源
        :return:
        """
        if hasattr(self, 'session') and self.session:
            await self.session.close()
        if self.context:
            await self.context.close()

    @staticmethod
    async def block_resources(route):
        url = route.request.url

        # 阻止特定的视频CDN域名或路径模式
        video_patterns = [
            # "webtrncdn.com",
            # "VIDEOSEGMENTS",
            # ".mp4",
            # ".flv"
        ]

        if any(pattern in url for pattern in video_patterns):
            await route.abort()
        # 阻止其他不需要的资源类型
        elif route.request.resource_type in ["image", "media", "font", "video"]:
            await route.abort()
        else:
            await route.continue_()

    @staticmethod
    def get_headers() -> dict:
        """获取请求头"""
        return {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "connection": "keep-alive",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://cmeonline.cma-cmc.com.cn",
            "referer": "https://cmeonline.cma-cmc.com.cn/u/trainingV1/ssoHook.json?Referer=https://cmeonline.cma-cmc.com.cn/cms/login.htm",
            "sec-ch-ua": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
        }
