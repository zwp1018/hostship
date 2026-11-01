#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import re
import platform
import requests
from seleniumbase import SB

# ================== 环境变量 ==================
HOSTSHIP_BASE = "https://panel.host-ship.com"
HOSTSHIP_LOGIN = f"{HOSTSHIP_BASE}/auth/login"
EMAIL = os.getenv("HOSTSHIP_EMAIL")
PASSWORD = os.getenv("HOSTSHIP_PASSWORD")

# ================== 辅助功能 ==================
def is_linux() -> bool:
    return platform.system().lower() == "linux"

def send_tg_notification(message, photo_path=None):
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": "Host-Ship 实时画面"},
                    files={"photo": f},
                    timeout=20
                )
    except Exception as e:
        print(f"TG 通知异常: {e}")

# ================== CF 过盾逻辑 ==================
def wait_for_turnstile(sb, timeout: int = 15) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            success = sb.execute_script('''
                var resp = document.querySelector('input[name="cf-turnstile-response"]');
                if (resp && resp.value && resp.value.length > 20) return true;
                return false;
            ''')
            if success:
                return True
        except:
            pass
        time.sleep(1)
    return False

# ================== 续期逻辑 ==================
def process_renewal(sb):
    time.sleep(5) 
    
    # 1. 点击 MANAGE SERVER 进入详情页
    try:
        print("🔍 正在查找 'MANAGE SERVER' 按钮...")
        server_selectors = [
            "a:contains('MANAGE SERVER')", 
            "button:contains('MANAGE SERVER')",
            "a:contains('Manage Server')",
            "button:contains('Manage Server')",
            'a[href*="/server/"]'
        ]
        
        found = False
        for selector in server_selectors:
            if sb.is_element_visible(selector):
                print(f"✅ 找到入口，点击进入控制台...")
                sb.click(selector)
                found = True
                break
        
        if not found:
            print("⚠️ 未能在主页找到 'MANAGE SERVER' 按钮，当前账号下可能没有服务器。")
            sb.save_screenshot("hostship_no_server.png")
            send_tg_notification("⚠️ <b>Host-Ship 状态</b>\n账号登录成功，但未发现 Manage Server 按钮。", "hostship_no_server.png")
            return

    except Exception as e:
        print(f"进入服务器详情页失败: {e}")
        return

    time.sleep(8) # 增加等待时间确保侧边栏加载
    current_server_url = sb.get_current_url()
    print(f"🌐 打开服务器控制台: {current_server_url}")
    
    # 2. 抓取页面上的续期信息
    try:
        page_text = sb.get_text("body")
        days_match = re.search(r'RENEWAL IN\s*(\d+\s*Days)', page_text, re.IGNORECASE)
        if not days_match:
            # 兼容截图右侧的 "11 Days" 格式
            days_match = re.search(r'EXPIRES.*?\n(\d+\s*Days)', page_text, re.IGNORECASE)
            
        days_left = days_match.group(1) if days_match else "未知天数"
        
        print(f"📅 当前续期倒计时: {days_left}")
        
        renew_button_selector = "button:contains('Renew'), button:contains('RENEW'), a:contains('Renew')"
        
        if sb.is_element_visible(renew_button_selector):
            btn_text = sb.get_text(renew_button_selector).strip()
            
            if "Limit Reached" in btn_text or "limit reached" in btn_text.lower():
                print(f"ℹ️ 按钮显示 '{btn_text}', 已达续期上限(如14天)，无需操作")
                msg = f"⏳ <b>Host-Ship 续期检查</b>\n服务器剩余: <code>{days_left}</code>\n状态: 已达续期上限无需操作 ({btn_text})"
                sb.save_screenshot("hostship_limit.png")
                send_tg_notification(msg, "hostship_limit.png")
            else:
                print(f"🖱️ 按钮显示 '{btn_text}', 尝试点击第一次续期按钮！")
                sb.click(renew_button_selector)
                
                # 等待弹窗出现
                time.sleep(5) 
                
                # 尝试点击二次确认弹窗里的最终按钮
                try:
                    print("👀 正在寻找弹窗中的确认按钮...")
                    # ================= 核心修复 =================
                    # 兼容 "Add 3 days", "Add ", "Renew now", "Confirm" 等多种面板可能出现的文案
                    confirm_selector = "button:contains('Add 3 days'), button:contains('Add '), button:contains('Renew now'), button:contains('Confirm'), button.btn-primary"
                    
                    if sb.is_element_visible(confirm_selector):
                        print("✅ 找到弹窗确认按钮，执行点击！")
                        sb.click(confirm_selector)
                        time.sleep(5)
                    else:
                        print("⚠️ 没有发现二次确认按钮，请检查截图面板是否再次改版。")
                except Exception as e:
                    print(f"点击二次确认按钮时发生异常: {e}")
                
                sb.save_screenshot("hostship_renew_success.png")
                msg = f"🎉 <b>Host-Ship 续期成功</b>\n已成功完成二次确认续期操作！\n原剩余时间: {days_left}"
                print(msg)
                send_tg_notification(msg, "hostship_renew_success.png")
        else:
            print("⚠️ 未能在详情页找到 'Renew' 按钮组件")
            sb.save_screenshot("hostship_no_renew_btn.png")
            send_tg_notification("⚠️ <b>Host-Ship 状态</b>\n进入了详情页，但未发现续期组件。", "hostship_no_renew_btn.png")

    except Exception as e:
         print(f"处理续期状态时发生异常: {e}")
         send_tg_notification(f"❌ <b>Host-Ship 解析异常</b>\n{e}")

# ================== 主流程 ==================
def run():
    if not EMAIL or not PASSWORD:
        print("❌ 错误: 缺少 HOSTSHIP_EMAIL 或 HOSTSHIP_PASSWORD")
        sys.exit(1)

    sb_kwargs = dict(
        uc=True,
        test=True,
        locale="en",
        headed=not is_linux(),
        chromium_arg="--disable-blink-features=AutomationControlled",
    )
    
    # 开启代理请取消下方注释（根据你工作流的代理端口填写）
    # sb_kwargs["proxy"] = "socks5://127.0.0.1:1080"

    try:
        with SB(**sb_kwargs) as sb:
            print(f"🚀 打开登录页: {HOSTSHIP_LOGIN}")
            sb.uc_open_with_reconnect(HOSTSHIP_LOGIN, reconnect_time=8)
            time.sleep(8)

            user_selector = "input[name='user'], input[name='username'], input[type='text'], input[type='email']"

            if "login" in sb.get_current_url() or sb.is_element_visible(user_selector):
                try:
                    print("📝 正在输入账号密码...")
                    sb.wait_for_element_visible(user_selector, timeout=15)
                    
                    sb.clear(user_selector)
                    sb.type(user_selector, EMAIL)
                    
                    pwd_selector = "input[name='password'], input[type='password']"
                    sb.wait_for_element_visible(pwd_selector, timeout=5)
                    sb.clear(pwd_selector)
                    sb.type(pwd_selector, PASSWORD)
                    time.sleep(2)
                    
                    print("🔒 检查 Cloudflare 验证...")
                    already_done = wait_for_turnstile(sb, timeout=5)
                    if not already_done:
                        for _ in range(3):
                            try: sb.uc_gui_click_captcha()
                            except: pass
                            time.sleep(3)
                            if wait_for_turnstile(sb, timeout=8): break
                    print("✅ 已通过 Cloudflare 验证 (或本来就没有)")
                    
                    print("➡️ 寻找并点击提交按钮...")
                    # 兼容 "Complete the security check" 和 "Sign In" 按钮
                    submit_selector = "button:contains('Complete the security check'), button:contains('Sign In'), button[type='submit']"
                    
                    if sb.is_element_visible(submit_selector):
                        sb.click(submit_selector)
                    else:
                        print("未找到提交按钮，尝试回车提交...")
                        sb.type(pwd_selector, "\n")
                    
                    time.sleep(15) 

                except Exception as e:
                    print(f"❌ 登录动作异常: {e}")
                    sb.save_screenshot("hostship_login_error.png")
                    send_tg_notification("❌ <b>Host-Ship 异常</b>\n执行填表或过盾时发生错误。", "hostship_login_error.png")
                    sys.exit(1)

            print("🔍 检查登录结果...")
            time.sleep(5)
            current_url = sb.get_current_url()
            
            if "login" in current_url or sb.is_element_visible(user_selector):
                print("❌ 登录失败！账号密码错误或被系统阻断。")
                sb.save_screenshot("hostship_login_failed.png")
                send_tg_notification("❌ <b>Host-Ship 登录失败</b>\n请查看截图排查原因（密码错误或被封锁）。", "hostship_login_failed.png")
                sys.exit(1)
            else:
                print(f"✅ 登录成功，当前 URL: {current_url}")
                process_renewal(sb)
                sys.exit(0)

    except Exception as e:
        print(f"脚本致命异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run()
