#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐歌单歌曲直链提取器
使用网易云音乐第三方API自动提取歌单中的所有歌曲直链
支持多线程并发处理和多种音质选择
"""

import requests
import json
import time
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs
from queue import Queue
import os

class NeteaseMusicDownloader:
    def __init__(self):
        # 网易云音乐API基础URL - 使用新的API服务器
        self.base_url = "https://163api.qijieya.cn"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Cookie': 'os=pc'  # 确保返回正常码率的URL
        })
        
        # 音质选项
        self.quality_levels = {
            '1': 'standard',    # 标准
            '2': 'higher',      # 较高
            '3': 'exhigh',      # 极高
            '4': 'lossless',    # 无损
            '5': 'hires',       # Hi-Res
            '6': 'jyeffect',    # 高清环绕声
            '7': 'sky',         # 沉浸环绕声
            '8': 'dolby',       # 杜比全景声
            '9': 'jymaster'     # 超清母带
        }
        
        # 线程安全的进度显示
        self.lock = threading.Lock()
        self.processed_count = 0
        self.total_count = 0
    
    def check_api_status(self):
        """检查API服务器状态"""
        try:
            print("正在检查API服务器状态...")
            # 尝试获取一个简单的API响应来检查状态
            response = self.session.post(f"{self.base_url}/search", data={'keywords': 'test'}, timeout=10)
            if response.status_code == 200:
                print("✓ API服务器连接正常")
                return True
            else:
                print(f"✗ API服务器返回错误: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ 无法连接到API服务器: {e}")
            return False
    
    def extract_playlist_id(self, playlist_url):
        """从歌单URL中提取歌单ID"""
        try:
            # 处理不同的URL格式
            if 'playlist' in playlist_url:
                # 从URL中提取ID
                parsed = urlparse(playlist_url)
                if parsed.query:
                    params = parse_qs(parsed.query)
                    if 'id' in params:
                        return params['id'][0]
                else:
                    # 从路径中提取ID
                    path_parts = parsed.path.split('/')
                    for i, part in enumerate(path_parts):
                        if part == 'playlist' and i + 1 < len(path_parts):
                            return path_parts[i + 1]
            else:
                # 假设直接输入的是ID
                return playlist_url
        except Exception as e:
            print(f"提取歌单ID时出错: {e}")
            return None
    
    def get_playlist_detail(self, playlist_id):
        """获取歌单详情"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/playlist/detail"
                data = {'id': playlist_id}
                
                print(f"正在获取歌单详情... (尝试 {attempt + 1}/{max_retries})")
                response = self.session.post(url, data=data, timeout=30)
                
                if response.status_code == 404:
                    print(f"歌单不存在或已被删除 (ID: {playlist_id})")
                    return None
                elif response.status_code == 403:
                    print(f"访问被拒绝，可能需要登录或歌单为私有")
                    return None
                elif response.status_code != 200:
                    print(f"API服务器返回错误: HTTP {response.status_code}")
                    if attempt < max_retries - 1:
                        print("等待3秒后重试...")
                        time.sleep(3)
                        continue
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                if data.get('code') == 200:
                    playlist = data.get('playlist', {})
                    if playlist:
                        print(f"成功获取歌单信息")
                        return playlist
                    else:
                        print("API返回成功但歌单信息为空")
                        return None
                else:
                    print(f"获取歌单详情失败: {data.get('msg', '未知错误')}")
                    if attempt < max_retries - 1:
                        print("等待3秒后重试...")
                        time.sleep(3)
                        continue
                    return None
                    
            except requests.exceptions.Timeout:
                print(f"请求超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    print("等待3秒后重试...")
                    time.sleep(3)
                    continue
                return None
            except requests.exceptions.ConnectionError:
                print(f"网络连接错误 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    print("等待3秒后重试...")
                    time.sleep(3)
                    continue
                return None
            except Exception as e:
                print(f"获取歌单详情时出错: {e}")
                if attempt < max_retries - 1:
                    print("等待3秒后重试...")
                    time.sleep(3)
                    continue
                return None
        
        print("所有重试都失败了")
        return None
    
    def get_playlist_tracks(self, playlist_id):
        """获取歌单中的所有歌曲 - 使用playlist/detail + song/detail的方式"""
        try:
            # 第一步：获取歌单详情，包含trackIds
            print(f"🔍 第一步：获取歌单详情...")
            url = f"{self.base_url}/playlist/detail"
            data = {'id': playlist_id}
            
            print(f"🔍 调试信息 - 请求URL: {url}")
            print(f"🔍 调试信息 - 请求参数: {data}")
            print(f"🔍 调试信息 - 请求方法: POST")
            
            response = self.session.post(url, data=data, timeout=30)
            
            print(f"🔍 调试信息 - 响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ 获取歌单详情失败: HTTP {response.status_code}")
                return []
            
            response.raise_for_status()
            result = response.json()
            
            print(f"🔍 调试信息 - 歌单详情API响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            if result.get('code') != 200:
                print(f"❌ 获取歌单详情失败: {result.get('msg', '未知错误')}")
                return []
            
            playlist = result.get('playlist', {})
            track_ids = playlist.get('trackIds', [])
            
            if not track_ids:
                print("❌ 歌单中没有找到歌曲")
                return []
            
            print(f"✅ 找到 {len(track_ids)} 首歌曲的ID")
            print(f"🔍 前5个trackIds: {track_ids[:5]}")
            
            # 第二步：使用trackIds获取歌曲详情
            print(f"🔍 第二步：获取歌曲详情...")
            song_ids = [track['id'] for track in track_ids]
            
            # 分批获取歌曲详情，每批50首
            batch_size = 50
            all_songs = []
            
            for i in range(0, len(song_ids), batch_size):
                batch_ids = song_ids[i:i+batch_size]
                print(f"🔍 正在获取第 {i+1}-{min(i+batch_size, len(song_ids))} 首歌曲详情...")
                
                url = f"{self.base_url}/song/detail"
                data = {'ids': ','.join(map(str, batch_ids))}
                
                print(f"🔍 调试信息 - 请求URL: {url}")
                print(f"🔍 调试信息 - 请求参数: {data}")
                print(f"🔍 调试信息 - 请求方法: POST")
                
                response = self.session.post(url, data=data, timeout=30)
                
                print(f"🔍 调试信息 - 响应状态码: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"❌ 获取歌曲详情失败: HTTP {response.status_code}")
                    continue
                
                response.raise_for_status()
                result = response.json()
                
                print(f"🔍 调试信息 - 歌曲详情API响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
                
                if result.get('code') == 200:
                    songs = result.get('songs', [])
                    all_songs.extend(songs)
                    print(f"✅ 成功获取 {len(songs)} 首歌曲详情")
                    print(f"🔍 前3首歌曲信息:")
                    for j, song in enumerate(songs[:3]):
                        print(f"   {j+1}. ID:{song.get('id')} - {song.get('name')} - {[ar.get('name') for ar in song.get('ar', [])]}")
                else:
                    print(f"❌ 获取歌曲详情失败: {result.get('msg', '未知错误')}")
                
                # 短暂延迟避免请求过快
                time.sleep(0.5)
            
            print(f"✅ 总共获取到 {len(all_songs)} 首歌曲")
            return all_songs
                
        except Exception as e:
            print(f"❌ 获取歌单歌曲时出错: {e}")
            return []
    
    def get_song_url_v1(self, song_id, quality_level):
        """获取歌曲直链 - 使用新版API支持不同音质"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/song/url/v1"
                data = {
                    'id': song_id,
                    'level': quality_level
                }
                
                # 添加随机延迟避免缓存
                import random
                delay = random.uniform(1.0, 3.0)
                print(f"⏳ 等待 {delay:.1f} 秒避免缓存...")
                time.sleep(delay)
                
                # 添加随机User-Agent避免被识别为机器人
                random_ua = f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(90, 120)}.0.0.0 Safari/537.36'
                self.session.headers.update({'User-Agent': random_ua})
                
                print(f"🔍 调试信息 - 请求URL: {url}")
                print(f"🔍 调试信息 - 请求参数: {data}")
                print(f"🔍 调试信息 - 请求方法: POST")
                print(f"🔍 调试信息 - User-Agent: {random_ua}")
                
                # 尝试使用GET请求
                response = self.session.get(url, params=data, timeout=15)
                
                print(f"🔍 调试信息 - 响应状态码: {response.status_code}")
                print(f"🔍 调试信息 - 响应头: {dict(response.headers)}")
                
                if response.status_code != 200:
                    print(f"❌ 请求失败，状态码: {response.status_code}")
                    if attempt < max_retries - 1:
                        print(f"⏳ 等待0.5秒后重试... (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(0.5)
                        continue
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                print(f"🔍 调试信息 - API响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
                
                if data.get('code') == 200 and data.get('data'):
                    song_data = data['data'][0]
                    if song_data.get('url'):
                        result = {
                            'url': song_data['url'],
                            'level': quality_level,
                            'br': song_data.get('br', 0),  # 比特率
                            'size': song_data.get('size', 0),  # 文件大小
                            'type': song_data.get('type', ''),  # 文件类型
                            'song_id': song_id  # 添加歌曲ID用于调试
                        }
                        print(f"✅ 成功获取直链: {result['url'][:50]}...")
                        return result
                    else:
                        print(f"❌ API返回成功但URL为空")
                        return None
                else:
                    print(f"❌ API返回错误: code={data.get('code')}, msg={data.get('msg', '未知错误')}")
                    if attempt < max_retries - 1:
                        print(f"⏳ 等待0.5秒后重试... (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(0.5)
                        continue
                    return None
                    
            except Exception as e:
                print(f"❌ 请求异常: {e}")
                if attempt < max_retries - 1:
                    print(f"⏳ 等待0.5秒后重试... (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(0.5)
                    continue
                return None
        
        print(f"❌ 所有重试都失败了")
        return None
    
    def process_single_song(self, song, quality_level):
        """处理单首歌曲 - 用于多线程"""
        song_id = song.get('id')
        song_name = song.get('name', '未知歌曲')
        artists = [artist.get('name', '') for artist in song.get('ar', [])]
        artist_names = ', '.join(artists) if artists else '未知歌手'
        
        # 获取歌曲直链
        url_info = self.get_song_url_v1(song_id, quality_level)
        
        with self.lock:
            self.processed_count += 1
            current = self.processed_count
            total = self.total_count
            
            if url_info:
                print(f"[{current}/{total}] ✓ {song_name} - {artist_names} (ID:{song_id}, {quality_level}, {url_info['br']}kbps)")
                return {
                    'name': song_name,
                    'artist': artist_names,
                    'url': url_info['url'],
                    'quality': quality_level,
                    'bitrate': url_info['br'],
                    'size': url_info['size'],
                    'type': url_info['type'],
                    'song_id': song_id
                }
            else:
                print(f"[{current}/{total}] ✗ {song_name} - {artist_names} (ID:{song_id}, 无法获取直链)")
                return None
    
    def select_quality(self):
        """选择音质等级"""
        print("\n请选择音质等级:")
        print("1. standard    - 标准音质")
        print("2. higher      - 较高音质")
        print("3. exhigh      - 极高音质")
        print("4. lossless    - 无损音质")
        print("5. hires       - Hi-Res音质")
        print("6. jyeffect    - 高清环绕声")
        print("7. sky         - 沉浸环绕声")
        print("8. dolby       - 杜比全景声")
        print("9. jymaster    - 超清母带")
        
        while True:
            choice = input("\n请输入选择 (1-9): ").strip()
            if choice in self.quality_levels:
                return self.quality_levels[choice]
            else:
                print("无效选择，请输入1-9之间的数字")
    
    def process_playlist(self, playlist_url_or_id):
        """处理歌单，提取所有歌曲直链"""
        # 提取歌单ID
        playlist_id = self.extract_playlist_id(playlist_url_or_id)
        if not playlist_id:
            print("无法提取歌单ID，请检查输入的URL或ID是否正确")
            return
        
        print(f"歌单ID: {playlist_id}")
        
        # 获取歌单详情（用于获取歌单名称）
        playlist_detail = self.get_playlist_detail(playlist_id)
        if not playlist_detail:
            return
        
        playlist_name = playlist_detail.get('name', '未知歌单')
        print(f"歌单名称: {playlist_name}")
        
        # 获取歌单中的所有歌曲
        songs_detail = self.get_playlist_tracks(playlist_id)
        if not songs_detail:
            print("无法获取歌单歌曲")
            return
        
        print(f"找到 {len(songs_detail)} 首歌曲")
        
        # 选择音质
        quality_level = self.select_quality()
        print(f"选择的音质: {quality_level}")
        
        # 设置进度计数
        self.total_count = len(songs_detail)
        self.processed_count = 0
        
        # 初始化文件
        self.init_file(playlist_name, quality_level)
        
        # 使用单线程处理歌曲，每获取一首就保存到文件
        success_count = 0
        
        print(f"\n开始单线程处理歌曲...")
        print(f"总共需要处理 {len(songs_detail)} 首歌曲")
        
        for i, song in enumerate(songs_detail, 1):
            print(f"\n正在处理第 {i}/{len(songs_detail)} 首歌曲...")
            
            song_id = song.get('id')
            song_name = song.get('name', '未知歌曲')
            artists = [artist.get('name', '') for artist in song.get('ar', [])]
            artist_names = ', '.join(artists) if artists else '未知歌手'
            
            print(f"歌曲信息: {song_name} - {artist_names} (ID: {song_id})")
            
            # 获取歌曲直链
            url_info = self.get_song_url_v1(song_id, quality_level)
            
            if url_info:
                print(f"✓ 成功获取直链: {url_info['br']}kbps")
                song_info = {
                    'name': song_name,
                    'artist': artist_names,
                    'url': url_info['url'],
                    'quality': quality_level,
                    'bitrate': url_info['br'],
                    'size': url_info['size'],
                    'type': url_info['type'],
                    'song_id': song_id
                }
                
                # 立即保存到文件
                self.append_song_to_file(song_info, i)
                success_count += 1
            else:
                print(f"✗ 无法获取直链")
            
            # 每处理一首歌后短暂延迟
            time.sleep(0.5)
        
        # 更新文件统计信息
        self.update_file_summary(success_count)
        
        print(f"\n✓ 处理完成！成功获取 {success_count} 首歌曲的直链")
        print(f"✓ 所有信息已保存到 list.txt")
    
    def init_file(self, playlist_name, quality_level):
        """初始化文件，写入头部信息"""
        try:
            filename = "list.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# 歌单: {playlist_name}\n")
                f.write(f"# 音质: {quality_level}\n")
                f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
            print(f"✓ 初始化文件: {filename}")
        except Exception as e:
            print(f"初始化文件时出错: {e}")
    
    def append_song_to_file(self, song, index):
        """将单首歌曲添加到文件"""
        try:
            filename = "list.txt"
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"{index}. {song['name']} - {song['artist']}\n")
                f.write(f"   歌曲ID: {song.get('song_id', '未知')}\n")
                f.write(f"   音质: {song['quality']} ({song['bitrate']}kbps)\n")
                f.write(f"   直链: {song['url']}\n")
                f.write(f"   大小: {song['size']} bytes\n")
                f.write(f"   类型: {song['type']}\n")
                f.write(f"   下载说明: 此直链需要添加Referer请求头才能正常访问\n")
                f.write(f"   推荐下载工具: IDM、Aria2、curl等支持自定义请求头的工具\n")
                f.write(f"   必要请求头: Referer: https://music.163.com/\n")
                f.write(f"   User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n")
                f.write("\n")
            
            print(f"✓ 已保存到文件: {song['name']} - {song['artist']}")
        except Exception as e:
            print(f"保存歌曲到文件时出错: {e}")
    
    def update_file_summary(self, total_count):
        """更新文件末尾的统计信息"""
        try:
            filename = "list.txt"
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 找到头部信息的位置
            header_end = 0
            for i, line in enumerate(lines):
                if line.startswith("=" * 50):
                    header_end = i + 2
                    break
            
            # 重新写入文件
            with open(filename, 'w', encoding='utf-8') as f:
                # 写入头部信息
                for i in range(header_end):
                    f.write(lines[i])
                
                # 写入歌曲信息
                song_lines = lines[header_end:]
                f.writelines(song_lines)
                
                # 添加统计信息
                f.write(f"\n" + "=" * 50 + "\n")
                f.write(f"# 统计信息\n")
                f.write(f"# 成功获取直链的歌曲: {total_count} 首\n")
                f.write(f"# 完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            
        except Exception as e:
            print(f"更新文件统计信息时出错: {e}")
    
    def save_to_file(self, song_links, playlist_name, quality_level):
        """保存歌曲直链到文件（保留兼容性）"""
        try:
            filename = "list.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# 歌单: {playlist_name}\n")
                f.write(f"# 音质: {quality_level}\n")
                f.write(f"# 歌曲数量: {len(song_links)}\n")
                f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, song in enumerate(song_links, 1):
                    f.write(f"{i}. {song['name']} - {song['artist']}\n")
                    f.write(f"   歌曲ID: {song.get('song_id', '未知')}\n")
                    f.write(f"   音质: {song['quality']} ({song['bitrate']}kbps)\n")
                    f.write(f"   直链: {song['url']}\n")
                    f.write(f"   大小: {song['size']} bytes\n")
                    f.write(f"   类型: {song['type']}\n")
                    f.write("\n")
            
            print(f"\n✓ 成功保存 {len(song_links)} 首歌曲的直链到 {filename}")
            print(f"✓ 成功获取直链的歌曲: {len(song_links)} 首")
            print(f"✓ 音质等级: {quality_level}")
            
        except Exception as e:
            print(f"保存文件时出错: {e}")

def main():
    print("网易云音乐歌单歌曲直链提取器 (多线程版)")
    print("=" * 50)
    
    downloader = NeteaseMusicDownloader()
    
    while True:
        print("\n请输入网易云音乐歌单链接或歌单ID:")
        print("示例链接: https://music.163.com/#/playlist?id=24381616")
        print("示例ID: 24381616")
        print("输入 'quit' 退出程序")
        
        user_input = input("\n请输入: ").strip()
        
        if user_input.lower() in ['quit', 'exit', '退出']:
            print("程序退出")
            break
        
        if not user_input:
            print("输入不能为空，请重新输入")
            continue
        
        print("\n开始处理歌单...")
        
        # 检查API服务器状态
        if not downloader.check_api_status():
            print("API服务器不可用，请稍后再试")
            continue
        
        downloader.process_playlist(user_input)
        print("\n处理完成!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
    input("按回车键退出...") 