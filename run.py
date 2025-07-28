#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐歌单歌曲直链提取器 - 命令行版本
使用方法: python run.py [歌单链接或ID]
"""

import sys
import os
from music_downloader import NeteaseMusicDownloader

def main():
    if len(sys.argv) != 2:
        print("使用方法: python run.py [歌单链接或ID]")
        print("示例: python run.py https://music.163.com/#/playlist?id=24381616")
        print("示例: python run.py 24381616")
        sys.exit(1)
    
    playlist_input = sys.argv[1]
    
    print("网易云音乐歌单歌曲直链提取器")
    print("=" * 40)
    
    downloader = NeteaseMusicDownloader()
    downloader.process_playlist(playlist_input)
    
    print("\n程序执行完成!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        sys.exit(1) 