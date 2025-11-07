# file: utils/logger_manager.py
import logging
import os
from typing import Optional


class LoggerManager:
    _instance = None
    _loggers = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_logger(cls, name: str,
                   log_file: Optional[str] = None,
                   level=logging.DEBUG,
                   console_level=None,
                   file_level=None) -> logging.Logger:
        """
        获取一个带有指定名称的日志记录器。

        :param name: 日志记录器的名称（通常为模块名）
        :param log_file: 日志文件路径（可选）
        :param level: 日志等级，默认 DEBUG
        :param console_level: 控制台输出等级（默认与level相同）
        :param file_level: 文件输出等级（默认与level相同）
        :return: 配置好的 logger 对象
        """
        if name in cls._loggers:
            return cls._loggers[name]

        logger = logging.getLogger(name)

        # 设置默认值
        if console_level is None:
            console_level = level
        if file_level is None:
            file_level = level

        # 设置 logger 的最低级别为两个中较低的那个
        logger.setLevel(min(console_level, file_level))

        # 如果没有添加处理器，则添加默认控制台处理器
        if not logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(console_level)
            logger.addHandler(console_handler)

            # 文件处理器
            if log_file:
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setFormatter(formatter)
                file_handler.setLevel(file_level)
                logger.addHandler(file_handler)

        cls._loggers[name] = logger
        return logger

    @classmethod
    def get_user_logger(cls, username: str,
                        level=logging.DEBUG,  # 改为DEBUG
                        console_level=logging.INFO,
                        file_level=None) -> logging.Logger:
        """
        为特定用户创建专属日志记录器
        """
        log_file = f"logs/user/{username}.log"
        return cls.get_logger(f"user.{username}", log_file, level, console_level, file_level)

    @classmethod
    def get_module_logger(cls, module_name: str,
                          level=logging.DEBUG,  # 改为DEBUG
                          console_level=logging.INFO,
                          file_level=None) -> logging.Logger:
        """
        为特定模块创建日志记录器
        """
        return cls.get_logger(f"module.{module_name}", level=level, console_level=console_level, file_level=file_level)

    @classmethod
    def get_user_module_logger(cls, username: str, module_name: str,
                               level=logging.DEBUG,  # 改为DEBUG
                               console_level=logging.INFO,
                               file_level=None) -> logging.Logger:
        """
        为特定用户和模块组合创建日志记录器
        """
        log_file = f"logs/user/{username}/{module_name}.log"
        return cls.get_logger(f"user.{username}.{module_name}", log_file, level, console_level, file_level)


# 全局访问点
get_logger = LoggerManager.get_logger
get_user_logger = LoggerManager.get_user_logger
get_module_logger = LoggerManager.get_module_logger
get_user_module_logger = LoggerManager.get_user_module_logger
