#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐直链下载器
用于下载list.txt中的歌曲直链，自动添加必要的请求头避免403错误
"""

import requests
import os
import time
import re
from urllib.parse import urlparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

class SongDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Range': 'bytes=0-'  # 支持断点续传
        })
        
        # 创建下载目录
        self.download_dir = "downloads"
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
    
    def parse_list_file(self, filename="list.txt"):
        """解析list.txt文件，提取歌曲信息"""
        songs = []
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用正则表达式提取歌曲信息
            pattern = r'(\d+)\.\s*(.+?)\s*-\s*(.+?)\s*\n\s*歌曲ID:\s*(\d+)\s*\n\s*音质:\s*(.+?)\s*\((\d+)kbps\)\s*\n\s*直链:\s*(.+?)\s*\n\s*大小:\s*(\d+)\s*bytes\s*\n\s*类型:\s*(.+?)\s*\n'
            matches = re.findall(pattern, content, re.MULTILINE)
            
            for match in matches:
                song = {
                    'index': int(match[0]),
                    'name': match[1].strip(),
                    'artist': match[2].strip(),
                    'song_id': match[3],
                    'quality': match[4].strip(),
                    'bitrate': int(match[5]),
                    'url': match[6].strip(),
                    'size': int(match[7]),
                    'type': match[8].strip()
                }
                songs.append(song)
            
            print(f"✓ 成功解析 {len(songs)} 首歌曲")
            return songs
            
        except Exception as e:
            print(f"❌ 解析文件失败: {e}")
            return []
    
    def sanitize_filename(self, filename):
        """清理文件名，移除非法字符"""
        # 移除或替换Windows文件名中的非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        filename = re.sub(illegal_chars, '_', filename)
        # 限制文件名长度
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def download_song(self, song, max_retries=3):
        """下载单首歌曲"""
        try:
            # 构建文件名
            filename = f"{song['index']:03d}. {song['name']} - {song['artist']}.{song['type']}"
            filename = self.sanitize_filename(filename)
            filepath = os.path.join(self.download_dir, filename)
            
            # 如果文件已存在且大小正确，跳过下载
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                if abs(file_size - song['size']) < 1024:  # 允许1KB的误差
                    print(f"✓ [{song['index']:03d}] 文件已存在，跳过: {filename}")
                    return True
            
            print(f"⏳ [{song['index']:03d}] 开始下载: {filename}")
            
            for attempt in range(max_retries):
                try:
                    response = self.session.get(song['url'], stream=True, timeout=30)
                    
                    if response.status_code == 200 or response.status_code == 206:
                        # 获取文件大小
                        total_size = int(response.headers.get('content-length', song['size']))
                        
                        with open(filepath, 'wb') as f:
                            downloaded = 0
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    
                                    # 显示下载进度
                                    if total_size > 0:
                                        progress = (downloaded / total_size) * 100
                                        print(f"\r⏳ [{song['index']:03d}] 下载进度: {progress:.1f}% ({downloaded}/{total_size} bytes)", end='', flush=True)
                        
                        print(f"\n✅ [{song['index']:03d}] 下载完成: {filename}")
                        return True
                        
                    elif response.status_code == 403:
                        print(f"❌ [{song['index']:03d}] 403错误，可能需要更新请求头")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        return False
                        
                    else:
                        print(f"❌ [{song['index']:03d}] HTTP {response.status_code}")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        return False
                        
                except Exception as e:
                    print(f"❌ [{song['index']:03d}] 下载异常: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return False
            
            return False
            
        except Exception as e:
            print(f"❌ [{song['index']:03d}] 下载失败: {e}")
            return False
    
    def download_all_songs(self, songs, max_workers=3):
        """并发下载所有歌曲"""
        print(f"\n🚀 开始下载 {len(songs)} 首歌曲...")
        print(f"📁 下载目录: {os.path.abspath(self.download_dir)}")
        print(f"🔧 并发数: {max_workers}")
        
        success_count = 0
        failed_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_song = {executor.submit(self.download_song, song): song for song in songs}
            
            # 处理完成的任务
            for future in as_completed(future_to_song):
                song = future_to_song[future]
                try:
                    result = future.result()
                    if result:
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    print(f"❌ [{song['index']:03d}] 任务异常: {e}")
                    failed_count += 1
        
        print(f"\n📊 下载完成!")
        print(f"✅ 成功: {success_count} 首")
        print(f"❌ 失败: {failed_count} 首")
        print(f"📁 文件保存在: {os.path.abspath(self.download_dir)}")

def main():
    print("网易云音乐直链下载器")
    print("=" * 50)
    
    downloader = SongDownloader()
    
    # 检查list.txt文件
    if not os.path.exists("list.txt"):
        print("❌ 未找到 list.txt 文件，请先运行 music_downloader.py 生成歌曲列表")
        return
    
    # 解析歌曲列表
    songs = downloader.parse_list_file()
    if not songs:
        print("❌ 没有找到可下载的歌曲")
        return
    
    # 显示歌曲列表
    print(f"\n📋 找到 {len(songs)} 首歌曲:")
    for song in songs[:5]:  # 只显示前5首
        print(f"   {song['index']:03d}. {song['name']} - {song['artist']} ({song['quality']}, {song['bitrate']}kbps)")
    if len(songs) > 5:
        print(f"   ... 还有 {len(songs) - 5} 首歌曲")
    
    # 询问用户是否继续
    choice = input(f"\n是否开始下载这 {len(songs)} 首歌曲? (y/n): ").strip().lower()
    if choice not in ['y', 'yes', '是']:
        print("取消下载")
        return
    
    # 询问并发数
    try:
        max_workers = int(input("请输入并发下载数 (建议1-5): ").strip() or "3")
        max_workers = max(1, min(10, max_workers))  # 限制在1-10之间
    except ValueError:
        max_workers = 3
    
    # 开始下载
    downloader.download_all_songs(songs, max_workers)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n下载被用户中断")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
    input("按回车键退出...") 