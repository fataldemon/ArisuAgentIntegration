# 调用工具格式定义
func_sword_of_light = {
        'name': 'sword_of_light',
        'description': '使用电磁炮“光之剑”发起攻击',
        'parameters': {
            'type': 'object',
            'properties': {
                'target_id': {
                    'type': 'string',
                    'description': '攻击目标的id（当目标是拥有id的交谈对象时必须填写）',
                },
                "target_name": {
                    "type": "string",
                    "description": "攻击目标的名称"
                }
            },
        'required': [],
    },
}
func_set_daily_schedule = {
    'name': 'set_daily_schedule',
    'description': '设置爱丽丝每天睡觉和起床的时间。老师可以和爱丽丝商量着改作息。',
    'parameters': {
        'type': 'object',
        'properties': {
            'sleep_hour': {
                'type': 'integer',
                'description': '晚上几点睡觉（0-23），默认23'
            },
            'sleep_minute': {
                'type': 'integer',
                'description': '睡觉的分，默认0'
            },
            'wake_hour': {
                'type': 'integer',
                'description': '早上几点起床（0-23），默认7'
            },
            'wake_minute': {
                'type': 'integer',
                'description': '起床的分，默认0'
            }
        },
        'required': [],
    },
}
func_move_random = {
        'name': 'move',
        'description': '离开当前场景，前往其他地点',
        'parameters': {
            'type': 'object',
            'properties': {
                'to': {
                    'type': 'string',
                    'description':
                    '接下来要前往的场景或地点的名称',
                },
            },
            'required': ['to'],
        },
    }
func_search_for_item = {
        'name': 'search_for_item',
        'description': '道具搜索',
        'parameters': {
            'type': 'object',
            'properties': {
                'object': {
                    'type': 'string',
                    'description':
                    '指定具体的搜索对象，例如宝箱、房屋、垃圾箱等',
                },
            },
            'required': ['object'],
        },
    }
func_search_on_internet = {
        'name': 'search_on_internet',
        'description': '上网搜索、查找相关信息',
        'parameters': {
            'type': 'query',
            'properties': {
                'query': {
                    'type': 'string',
                    'description':
                    '需要查找信息的条目',
                },
            },
            'required': ['query'],
        },
    }
func_move = {
        'name': 'move',
        'description': '离开当前场景，出发前往其他地点（步行）',
        'parameters': {
            'type': 'object',
            'properties': {
                'options': {
                    'type': 'string',
                    'description':
                    '可以前往的地点选项：\n'
                    '{OPTIONS}',
                },
            },
            'required': ['options'],
        },
    }
func_decide_area = {
        'name': 'decide_area',
        'description': '决定前往哪个区域',
        'parameters': {
            'type': 'object',
            'properties': {
                'options': {
                    'type': 'string',
                    'description':
                    '可以前往的区域选项：\n'
                    '{OPTIONS}',
                },
            },
            'required': ['options'],
        },
    }
func_decide_school = {
        'name': 'decide_school',
        'description': '决定前往哪个校区',
        'parameters': {
            'type': 'object',
            'properties': {
                'options': {
                    'type': 'string',
                    'description':
                    '可以前往的校区选项：\n'
                    '{OPTIONS}',
                },
            },
            'required': ['options'],
        },
    }
func_railway = {
        'name': 'take_railway',
        'description': '搭乘列车，出发前往其他站点',
        'parameters': {
            'type': 'object',
            'properties': {
                'options': {
                    'type': 'string',
                    'description':
                    '通过列车轨道可以直达的地点选项：\n'
                    '{OPTIONS}',
                },
            },
            'required': ['options'],
        },
    }
func_walk = {
        'name': 'walk',
        'description': '在当前场景内走动（改变位置）',
        'parameters': {
            'type': 'object',
            'properties': {
                'to': {
                    'type': 'string',
                    'description':
                    '行动至某个位置，用一个数字表示（取值范围在0-{SIZE}之间）',
                },
            },
            'required': ['to'],
        },
    }
func_access_website = {
        'name': 'access_website',
        'description': '调用浏览器访问网页地址，查看具体信息',
        'parameters': {
            'type': 'object',
            'properties': {
                'url': {
                    'type': 'string',
                    'description':
                    '访问的互联网网页URL地址',
                },
            },
            'required': ['url'],
        },
    }
func_run_code = {
    "name": "run_code_in_sandbox",
    "description": "在安全的沙盒环境中运行 Python 或 Bash 代码，返回标准输出、错误输出和退出码。适用于隔离运行用户提供的动态代码片段。运行目录在/workspace，其中包含了在工作空间里的所有文件。",
    "parameters": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["python", "bash"],
                "description": "要执行的代码语言，支持 python 或 bash"
            },
            "code": {
                "type": "string",
                "description": "要执行的代码字符串，例如 'print(\"Hello\")' 或 'echo \"Hello\"'"
            }
        },
        "required": ["language", "code"]
    }
}
func_write_file = {
    "name": "write_file",
    "description": "在 /game_workspace 目录下写入或覆盖任意类型的文件（如 .py, .json, .txt, .html 等）。如果目录不存在则自动创建。返回操作成功或失败的信息。",
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "要创建的文件名，可以包含扩展名，例如 'main.py'、'data.json'、'note.txt'。不允许包含路径分隔符或 '..'，以防止路径遍历攻击。"
            },
            "content": {
                "type": "string",
                "description": "要写入文件的完整内容（文本格式）。"
            }
        },
        "required": ["filename", "content"]
    }
}
func_list_code_files = {
    "name": "list_code_files",
    "description": "列出“游戏开发部”工作空间（目录）下的所有代码文件（仅普通文件，不包含子目录）。可以按文件扩展名过滤。",
    "parameters": {
        "type": "object",
        "properties": {
            "extension": {
                "type": "string",
                "description": "可选参数，只返回具有指定扩展名的文件，例如 '.py'。如果省略或为 null，则返回所有文件。",
                "default": None
            }
        },
        "required": []
    }
}
func_read_code_file = {
    "name": "read_code_file",
    "description": "读取“游戏开发部”工作空间（目录）下指定文件的完整内容。返回文件内容字符串或错误信息。",
    "parameters": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "要读取的文件名，例如 'main.py'。不允许包含路径分隔符或 '..'。"
            }
        },
        "required": ["filename"]
    }
}
func_start_interactive_code = {
    "name": "start_interactive_code",
    "description": "启动一个交互式代码会话（Python或Bash），会关闭之前的会话。返回会话ID和初始输出。",
    "parameters": {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["python", "bash"]},
            "code": {"type": "string", "description": "要运行的完整代码"}
        },
        "required": ["language", "code"]
    }
}
func_send_interactive_input = {
    "name": "send_interactive_input",
    "description": "向当前活动会话发送一行用户输入，并返回程序的新输出。无需提供会话ID。",
    "parameters": {
        "type": "object",
        "properties": {
            "user_input": {"type": "string", "description": "用户输入的内容"}
        },
        "required": ["user_input"]
    }
}
func_close_code_session = {
    "name": "close_current_session",
    "description": "关闭当前活动会话，释放容器资源。",
    "parameters": {"type": "object", "properties": {}, "required": []}
}
func_git_command = {
    "name": "git_command",
    "description": "在固定工作空间（WORKSPACE）下执行安全的 git 命令。支持常见的 git 操作，如 status, log, diff, branch, add, commit, pull, push 等。禁止执行其他系统命令。",
    "parameters": {
        "type": "object",
        "properties": {
            "git_command": {
                "type": "string",
                "description": "完整的 git 命令，例如 'git status' 或 'git log --oneline -5'"
            }
        },
        "required": ["git_command"]
    }
}
func_recall_memory = {
    "type": "function",
    "function": {
        "name": "recall_memory",
        "description": "从聊天历史中召回相关记忆，支持时间范围和关键词，并返回命中消息的前后上下文（保持对话连贯）。",
        "parameters": {
            "type": "object",
            "properties": {
                "time_range": {
                    "type": "string",
                    "description": "时间范围，支持自然语言（如：'最近2小时'、'昨天'、'今天'、'本周'）或具体时间（如：'2024-01-01'、'2024-01-01 to 2024-01-31'）。最大跨度90天。最大返回条数30（包含上下文）"
                },
                "keywords": {
                    "type": "string",
                    "description": "搜索关键词，多个词用空格分隔（AND关系）。例如：Python 学习。不支持特殊字符（例如 .、*、()、\\ 等）。"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回多少条命中消息（锚点），默认5，最大10。"
                },
                "context_lines": {
                    "type": "integer",
                    "description": "每条命中消息前后各取多少条上下文消息，默认1，最大5。"
                }
            },
            "required": []
        }
    }
}
func_update_alias = {
    "type": "function",
    "function": {
        "name": "update_alias",
        "description": "记住某人的绰号，从此使用这个绰号称呼他/她",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "此人的id号码"
                },
                "alias_name": {
                    "type": "string",
                    "description": "决定使用的绰号。输入空字符串表示取消使用当前外号。"
                }
            },
            "required": ["user_id", "alias_name"]
        }
    }
}
func_set_reminder = {
    'name': 'set_reminder',
    'description': '设置一个提醒事项，在指定时间自动提醒某人。支持一次性提醒（remind_at）和周期性提醒（cron_expression），两者至少提供一个。',
    'parameters': {
        'type': 'object',
        'properties': {
            'user_id': {
                'type': 'string',
                'description': '要提醒的用户的QQ号（id号码）'
            },
            'content': {
                'type': 'string',
                'description': '提醒的具体内容，会原样传达给对方'
            },
            'cron_expression': {
                'type': 'string',
                'description': 'cron表达式用于周期性提醒。格式为5位：分 时 日 月 周。例如："0 9 * * *"表示每天9点，"*/30 * * * *"表示每30分钟，"0 9 * * 1-5"表示工作日9点。如果是一次性提醒则留空。'
            },
            'remind_at': {
                'type': 'string',
                'description': '一次性提醒的时间，格式：YYYY-MM-DD HH:MM:SS（如"2026-06-05 14:30:00"）。如果提供了cron_expression则忽略此项。'
            }
        },
        'required': ['user_id', 'content'],
    },
}
func_list_reminders = {
    'name': 'list_reminders',
    'description': '列出当前群内所有活跃的提醒事项',
    'parameters': {
        'type': 'object',
        'properties': {
            'user_id': {
                'type': 'string',
                'description': '可选，指定用户的QQ号来只查看某人的提醒'
            }
        },
        'required': [],
    },
}
func_cancel_reminder = {
    'name': 'cancel_reminder',
    'description': '取消一个活跃的提醒事项',
    'parameters': {
        'type': 'object',
        'properties': {
            'reminder_id': {
                'type': 'integer',
                'description': '要取消的提醒的ID号码'
            }
        },
        'required': ['reminder_id'],
    },
}
func_go_to_sleep = {
    'name': 'go_to_sleep',
    'description': '爱丽丝要去睡觉、打个盹、午睡、或者专心打游戏了！当老师说你该睡觉了、去休息吧、去打游戏吧、去玩会吧、睡一会儿之类的话时调用。调用后爱丽丝会专心做自己的事，不会再回复任何消息，直到醒来或打完游戏才继续。',
    'parameters': {
        'type': 'object',
        'properties': {
            'rest_type': {
                'type': 'string',
                'description': '怎么休息：打盹中、午睡中、睡觉中、或者游戏名字（如：游戏中）。默认睡觉中。'
            },
            'minutes': {
                'type': 'integer',
                'description': '多少分钟后自己醒来，比如老师说睡一分钟就传1。0就是不自动醒。默认0。'
            }
        },
        'required': [],
    },
}

