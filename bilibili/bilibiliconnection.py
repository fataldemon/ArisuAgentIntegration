import asyncio
import os
import threading

from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import blivedm
import blivedm.models.open_live as open_models
import blivedm.models.web as web_models
from llmClient.llm_manager import LLMManager

load_dotenv()


class BilibiliClient:
    ACCESS_KEY_ID = ""
    ACCESS_KEY_SECRET = ""
    APP_ID = ""
    ROOM_OWNER_AUTH_CODE = ""
    llm_manager = None

    def __init__(self, access_key_id: str, access_key_secret: str, app_id: int, room_owner_id: str,
                 llm_manager: LLMManager):
        self.client = None
        self.ACCESS_KEY_ID = access_key_id
        self.ACCESS_KEY_SECRET = access_key_secret
        self.APP_ID = app_id
        self.ROOM_OWNER_AUTH_CODE = room_owner_id
        self.thread = None
        self.loop = None
        self.is_running = False
        self.llm_manager = llm_manager

    def start_client(self):
        if self.is_running:
            print("客户端已经在运行！")
            return

        self.is_running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.start()
        print("bilibili直播间连接开启")

    async def stop_and_close_with_timeout(self, client, timeout=20):
        try:
            await asyncio.wait_for(client.stop_and_close(), timeout)
        except asyncio.TimeoutError:
            print("Warning: 关闭 WebSocket 连接超时，可能 Bilibili 服务器未响应")

    def stop_client(self):
        if not self.is_running:
            print("客户端未运行！")
            return

        self.is_running = False
        asyncio.run_coroutine_threadsafe(
            self.stop_and_close_with_timeout(self.client, timeout=10), self.loop
        )
        self.thread.join()
        print("bilibili直播间连接关闭")

    async def run_single_client(self):
        """
        演示监听一个直播间
        """
        self.client = blivedm.OpenLiveClient(
            access_key_id=self.ACCESS_KEY_ID,
            access_key_secret=self.ACCESS_KEY_SECRET,
            app_id=self.APP_ID,
            room_owner_auth_code=self.ROOM_OWNER_AUTH_CODE,
        )
        handler = MyHandler(llm_manager=self.llm_manager)
        self.client.set_handler(handler)
        print("Connection start...")
        self.client.start()
        try:
            await self.client.join()
        finally:
            await self.client.stop_and_close()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.run_single_client())


class MyHandler(blivedm.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=5)

    def __init__(self, llm_manager: LLMManager):
        self.llm_manager = llm_manager

    def _on_heartbeat(self, client: blivedm.BLiveClient, message: web_models.HeartbeatMessage):
        print(f'[{client.room_id}] 心跳')

    def _on_open_live_danmaku(self, client: blivedm.OpenLiveClient, message: open_models.DanmakuMessage):
        print(f'[{message.room_id}] {message.uname}：{message.msg}')
        loop = asyncio.get_running_loop()
        loop.run_in_executor(self.executor, self.llm_manager.call_llm_by_comments, f"（用户“{message.uname}”说） {message.msg}")

    def _on_open_live_gift(self, client: blivedm.OpenLiveClient, message: open_models.GiftMessage):
        coin_type = '金瓜子' if message.paid else '银瓜子'
        total_coin = message.price * message.gift_num
        print(f'[{message.room_id}] {message.uname} 赠送{message.gift_name}x{message.gift_num}'
              f' （{coin_type}x{total_coin}）')

    def _on_open_live_buy_guard(self, client: blivedm.OpenLiveClient, message: open_models.GuardBuyMessage):
        print(f'[{message.room_id}] {message.user_info.uname} 购买 大航海等级={message.guard_level}')

    def _on_open_live_super_chat(
        self, client: blivedm.OpenLiveClient, message: open_models.SuperChatMessage
    ):
        print(f'[{message.room_id}] 醒目留言 ¥{message.rmb} {message.uname}：{message.message}')

    def _on_open_live_super_chat_delete(
        self, client: blivedm.OpenLiveClient, message: open_models.SuperChatDeleteMessage
    ):
        print(f'[{message.room_id}] 删除醒目留言 message_ids={message.message_ids}')

    def _on_open_live_like(self, client: blivedm.OpenLiveClient, message: open_models.LikeMessage):
        print(f'[{message.room_id}] {message.uname} 点赞')
        loop = asyncio.get_running_loop()
        loop.run_in_executor(self.executor, self.llm_manager.call_llm_by_comments,
                             f"（一位用户“{message.uname}”点赞了爱丽丝的直播间） ")

    def _on_open_live_enter_room(self, client: blivedm.OpenLiveClient, message: open_models.RoomEnterMessage):
        print(f'[{message.room_id}] {message.uname} 进入房间')
        # loop = asyncio.get_running_loop()
        # loop.run_in_executor(self.executor, self.llm_manager.call_llm_by_comments,
        #                      f"(一位用户“{message.uname}”进入了爱丽丝的直播间) ")

    def _on_open_live_start_live(self, client: blivedm.OpenLiveClient, message: open_models.LiveStartMessage):
        print(f'[{message.room_id}] 开始直播')
        loop = asyncio.get_running_loop()
        loop.run_in_executor(self.executor, self.llm_manager.call_llm_by_comments,
                             f"（爱丽丝开始了直播） ")

    def _on_open_live_end_live(self, client: blivedm.OpenLiveClient, message: open_models.LiveEndMessage):
        print(f'[{message.room_id}] 结束直播')


if __name__ == '__main__':
    # 在开放平台申请的开发者密钥
    ACCESS_KEY_ID = os.environ.get("ACCESS_KEY_ID")
    ACCESS_KEY_SECRET = os.environ.get("ACCESS_KEY_SECRET")
    # 在开放平台创建的项目ID
    APP_ID = int(os.environ.get("APP_ID"))
    # 主播身份码
    ROOM_OWNER_AUTH_CODE = os.environ.get("ROOM_OWNER_AUTH_CODE")
    client = BilibiliClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, APP_ID, ROOM_OWNER_AUTH_CODE)
    client.start_client()
    input("Press Enter to stop...")  # 主线程在此阻塞
    client.stop_client()




