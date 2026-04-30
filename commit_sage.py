import subprocess
import os
import requests

# --- 配置区 ---
API_KEY = "你的API_KEY"
API_URL = "https://api.openai.com/v1/chat/completions" # 如果用Gemini或DeepSeek换成对应地址
MODEL = "gpt-3.5-turbo" # 或者 deepseek-chat, gemini-pro 等
# --------------

def get_git_diff():
    """获取当前暂存区代码改动的差异"""
    try:
        # 获取已 add 但未 commit 的改动
        diff = subprocess.check_output(["git", "diff", "--cached"], text=True)
        return diff
    except Exception as e:
        return f"获取diff失败: {e}"

def generate_commit_message(diff):
    """调用 AI 生成 commit 信息"""
    if not diff.strip():
        return "没有检测到暂存的代码改动，请先执行 git add ."

    prompt = f"请根据以下代码改动，写一个简短的 Git Commit Message（使用 Conventional Commits 规范，如 feat: xxx 或 fix: xxx）：\n\n{diff}"
    
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = requests.post(API_URL, headers=headers, json=data)
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"AI 生成失败: {e}"

def main():
    diff = get_git_diff()
    if not diff.strip():
        print("❌ 暂存区为空，请先 git add 文件")
        return

    print("🤖 AI 正在分析代码改动...")
    message = generate_commit_message(diff)
    print(f"\n📝 建议的提交信息:\n{message}\n")

    confirm = input("是否使用此信息提交？(y/n): ")
    if confirm.lower() == 'y':
        subprocess.run(["git", "commit", "-m", message])
        print("✅ 提交成功！")
    else:
        print("已取消。")

if __name__ == "__main__":
    main()