import base64, requests, json, os, sys
from pathlib import Path
from huggingface_hub import HfApi, login

u = "usha.thapaz488@gmail.com"
p = "9#w^^95!x48C8jM"

s = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://huggingface.co/login',
    'Origin': 'https://huggingface.co'
}
res = s.post('https://huggingface.co/login', data={'username': u, 'password': p}, headers=headers)
print('Login Status:', res.status_code, 'URL:', res.url)

cookie_token = s.cookies.get('token')
print('Session Token retrieved:', bool(cookie_token))

w = requests.get('https://huggingface.co/api/whoami-v2', headers={'Authorization': f'Bearer {cookie_token}'})
whoami = w.json()
username = whoami.get('name')
print('Logged in as user:', username)
print('Email:', whoami.get('email'))

api = HfApi(token=cookie_token)

repo_id = fg{username}/ai-video-studio'
print(f'Creating Space {repo_id}...')
try:
    repo = api.create_repo(
        repo_id=repo_id,
        repo_type='space',
        space_sdk='gradio',
        space_hardware='zero-a10g',
        exist_ok=True
    )
    print('Space repository created successfully:', repo)
except Exception as e:
    print('Create repo notice / result:', e)

space_dir = Path('hf_space_demo').resolve()
print(f'Uploading files from {space_dir} to {repo_id}...')
try:
    api.upload_folder(
        folder_path=str(space_dir),
        repo_id=repo_id,
        repo_type='space',
        ignore_patterns=['__pycache__/*', '*.pyc', 'deploy.py']
    )
    print('=' * 60)
    print('🎉 SPACE DEPLOYED SUCCESSFULLY!')
    print(f'🕗 https://huggingface.co/spaces/{repo_id}')
    print('=' * 60)
except Exception as e:
    print('Upload folder error:', e)
