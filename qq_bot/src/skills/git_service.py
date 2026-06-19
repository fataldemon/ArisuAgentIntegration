# services/git_service.py
import asyncio
import subprocess
import shlex
import re
from pathlib import Path

# 从配置导入 WORKSPACE 路径（或直接定义）
from src.skills.game_development import WORKSPACE  # 假设你有这个配置，或者从 interactive_sandbox 导入


def is_safe_git_command(command: str) -> bool:
    """
    检查 git 命令是否安全，自动忽略引号内的内容（如提交信息）。
    允许管道、逻辑符、只读系统命令，禁止引号外的注入和写入操作。
    """
    if not isinstance(command, str):
        return False

    def strip_quoted_parts(s: str) -> str:
        """移除所有引号内的内容（保留引号外壳），只留下未被引号包裹的结构代码"""
        result = []
        lex = shlex.shlex(s, posix=True)
        lex.whitespace = ''  # 我们不按空白分割，只提取 token 类型
        lex.wordchars += '|&<>;()$`'  # 特殊字符也算作单词的一部分
        try:
            for token in lex:
                if token in ('"', "'"):
                    # 这是引号开始，跳过直到匹配的引号
                    lex.escapedquotes = token
                    quoted = lex.get_token()
                    # 跳过引号内的内容
                    result.append(token)  # 开引号
                    result.append(' ' * len(quoted))  # 用空格填充内容
                    result.append(token)  # 闭引号
                else:
                    result.append(token)
        except ValueError:
            # 如果引号不匹配，退化到直接返回原字符串（但这种情况很少）
            return s
        return ''.join(result)

    cmd = command.strip()
    if not cmd:
        return False

    # 去引号版本（引号内字符被替换为空格）
    clean_cmd = strip_quoted_parts(cmd)

    # 1. 禁止引号外的命令分隔符 ; 和命令替换 ` $(
    if re.search(r'[;`]|\$\(', clean_cmd):
        return False

    # 2. 禁止输出重定向 > 或 >>
    if re.search(r'(?<![<>])>(?!>)|>>', clean_cmd):
        return False

    # 3. 禁止危险写入命令（黑名单）
    dangerous = re.compile(
        r'\b(rm|mv|cp|dd|tee|chmod|chown|chattr|kill|pkill|killall|'
        r'shutdown|reboot|halt|poweroff|mkfs|fdisk|curl|wget|'
        r'ssh|scp|rsync|nc|telnet|mount|umount|pkg|apt|yum|dnf|pip|npm|gem)\b',
        re.IGNORECASE
    )
    if dangerous.search(clean_cmd):
        return False

    return True


def run_git_command_sync(command: str, timeout: int = 30):
    """
    同步执行 git 命令，工作目录固定为 WORKSPACE。
    返回 (stdout, stderr, returncode)
    """
    if not is_safe_git_command(command):
        return "", f"不安全的 git 命令：{command}", 1

    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"命令执行超时（{timeout}秒）", 124
    except Exception as e:
        return "", f"执行出错：{str(e)}", 1


async def git_command_service(git_command: str, timeout: int = 30) -> str:
    """
    在 WORKSPACE 目录下执行安全的 git 命令，返回结果（AI 友好格式）。
    """
    timeout = int(timeout)
    loop = asyncio.get_running_loop()
    stdout, stderr, retcode = await loop.run_in_executor(
        None, run_git_command_sync, git_command, timeout
    )

    if retcode == 0:
        if stdout:
            return f"（Git 命令执行成功）\n<输出>：\n{stdout}"
        else:
            return f"（Git 命令执行成功，无输出）"
    else:
        error_msg = stderr if stderr else stdout
        return f"（Git 命令执行失败，退出码 {retcode}）\n<错误>：\n{error_msg}"