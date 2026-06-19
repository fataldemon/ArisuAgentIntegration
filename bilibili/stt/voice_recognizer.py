import queue

import numpy as np
import sounddevice as sd
import threading
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess


def _init_model(model_dir, device, vad_model, vad_kwargs):
    """模型初始化方法"""
    if vad_kwargs is None:
        vad_kwargs = {"max_single_segment_time": 160000}

    return AutoModel(
        model=model_dir,
        trust_remote_code=True,
        remote_code="./model.py",
        vad_model=vad_model,
        vad_kwargs=vad_kwargs,
        device=device
    )


class VoiceRecognizer:
    def __init__(
            self,
            model_dir="iic/SenseVoiceSmall",
            device="cuda:0",
            vad_model="fsmn-vad",
            vad_kwargs=None,
            hotword='爱丽丝，Alice，天童爱丽丝',
            chunk_size=16000,
            buffer_duration=60,
            silence_threshold=0.1
    ):
        # 模型初始化
        self.model = _init_model(model_dir, device, vad_model, vad_kwargs)

        # 音频配置参数
        self.chunk_size = chunk_size
        self.silence_threshold = silence_threshold
        self.hotword = hotword

        # 音频缓冲区初始化
        self.audio_buffer = np.zeros(chunk_size * buffer_duration, dtype=np.float32)
        self.buffer_offset = 0
        self.chunk_num = 0
        self.buffer_clear_offset = 0
        self.text_buffer = ""
        self.text_queue = queue.Queue()

        # 控制变量
        self.is_recording = False
        self.stream_thread = None

    def _decode(self, buffer):
        """执行语音识别"""
        res = self.model.generate(
            input=buffer,
            cache={},
            language="auto",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
            hotword=self.hotword
        )
        return rich_transcription_postprocess(res[0]["text"])  # 确保该函数已定义

    def _audio_callback(self, indata, frames, time, status):
        """音频处理回调函数"""
        if status:
            print(status, flush=True)

        # 计算当前音频块的音量
        volume_norm = np.linalg.norm(indata) * 10
        if volume_norm > self.silence_threshold and self.chunk_num < 50:
            # 将新音频数据复制到缓冲区
            self.audio_buffer[self.buffer_offset:self.buffer_offset + frames] = indata[:, 0]
            self.buffer_offset += frames

            # 当缓冲区达到设定大小时进行处理
            if self.buffer_offset >= (self.chunk_num + 1) * self.chunk_size:
                self.chunk_num += 1
                self.text_buffer = self._decode(self.audio_buffer[:self.buffer_offset])
                if self.text_buffer:
                    print(f"Transcription: {self.text_buffer}, Chunk Numbers: {self.chunk_num}", flush=True)
                else:
                    self.text_buffer = ""
                    # 滚动缓冲区
                    self.audio_buffer = np.roll(self.audio_buffer, -self.chunk_num * self.chunk_size)
                    self.buffer_offset -= self.chunk_num * self.chunk_size
                    self.chunk_num = 0
        else:
            if self.text_buffer:
                self.buffer_clear_offset += frames
                if self.buffer_clear_offset > self.chunk_size * 0.5:
                    if self.text_buffer:
                        print(f"Final Text: {self.text_buffer}", flush=True)
                        self.text_queue.put(self.text_buffer)
                    self.text_buffer = ""
                    # 滚动缓冲区
                    self.audio_buffer = np.roll(self.audio_buffer, -self.chunk_num * self.chunk_size)
                    self.buffer_offset -= self.chunk_num * self.chunk_size
                    self.chunk_num = 0

            # 重置缓冲区位置
            self.buffer_offset = 0

    def _start_streaming(self, device_id):
        """内部流式处理线程"""
        with sd.InputStream(
                device=device_id,
                callback=self._audio_callback,
                channels=1,
                samplerate=16000,
                blocksize=self.chunk_size
        ) as stream:
            print("Listening...")
            while self.is_recording:
                sd.sleep(1000)

    def start(self, device_id: int = 1, threshold: int = 0.1):
        """开始录音"""
        self.silence_threshold = threshold
        if not self.is_recording:
            self.is_recording = True
            self.stream_thread = threading.Thread(
                target=self._start_streaming,
                args=(device_id,),
                daemon=True
            )
            self.stream_thread.start()

    def stop(self):
        """停止录音"""
        if self.is_recording:
            self.is_recording = False
            if self.stream_thread is not None:
                self.stream_thread.join()
            print("Stream stopped")

    def get_latest_text(self):
        """获取最新识别结果"""
        return self.text_queue.get_nowait() if not self.text_queue.empty() else None


# 使用示例
if __name__ == "__main__":
    recognizer = VoiceRecognizer()
    recognizer.start()  # 开始录音
    input("Press Enter to stop...")  # 主线程在此阻塞
    recognizer.stop()
