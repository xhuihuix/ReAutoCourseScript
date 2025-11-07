from json import dumps
from typing import Optional

from aiohttp import ClientSession
from requests import post


async def recognize_captcha_async(api_url: str, token: str, base64_data: str) -> Optional[str]:
    """
    从指定 URL 异步识别验证码

    :param api_url: 验证码识别API的URL
    :param token: 验证码识别API的token
    :param base64_data: base64编码
    :return: 图片的验证码文本
    """
    try:
        # 验证码识别API URL
        api_url = api_url
        headers = {
            'Content-Type': 'application/json'
        }
        payload = {
            "token": token,
            "type": 10115,
            "image": base64_data
        }

        # 使用aiohttp进行异步请求
        async with ClientSession() as session:
            async with session.post(api_url, headers=headers, data=dumps(payload)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("code") == 10000:
                        captcha_text = result["data"]["data"]
                        return captcha_text
                    else:
                        print(f"API识别失败: {result.get('msg', '未知错误')}")
                else:
                    print(f"API请求失败，状态码: {response.status}")
    except Exception as e:
        print(f"验证码识别出错: {e}")

    return ""


def recognize_captcha(api_url: str, token: str, base64_data: str, ) -> str:
    """
    从指定 URL 识别验证码

    :param api_url: 验证码识别API的URL
    :param token: 验证码识别API的token
    :param base64_data: base64编码
    :return: 图片的 base64 编码字符串
    """
    try:

        # 调用验证码识别API
        api_url = api_url
        headers = {
            'Content-Type': 'application/json'
        }
        payload = {
            "token": token,
            "type": 10115,
            "image": base64_data
        }

        response = post(api_url, headers=headers, data=dumps(payload))

        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 10000:
                captcha_text = result["data"]["data"]
                print(f"验证码识别成功: {captcha_text}")
                return captcha_text
            else:
                print(f"API识别失败: {result.get('msg', '未知错误')}")
        else:
            print(f"API请求失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"验证码识别出错: {e}")

    return ""