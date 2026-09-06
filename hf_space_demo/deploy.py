import os
import sys
from pathlib import Path
from huggingface_hub import HfApi, login

def deploy_space(token: str, space_name: str = 'ai-video-studio', sdk: str = 'gradio'):
    token = token.strip()
    if not token.startswith('hf_'):
        print('Error: Invalid token. Hugging Face tokens start with hf_')
        return False
        
    print('Authenticating with Hugging Face...')
    try:
        login(token=token, add_to_git_credential=True)
        api = HfApi(token=token)
        user_info = api.whoami()
        username = user_info.get('name')
        print(f'Successfully logged in as user: {username}')
    except Exception as e:
        print(f'Authentication failed: {e}')
        return False

    repo_id = f'{username}/{space_name}'
    print(f'Creating Space repository: {repo_id} (SDK: {sdk})...')
    try:
        api.create_repo(
            repo_id=repo_id,
            repo_type='space',
            space_sdk=sdk,
            exist_ok=True,
            private=False
        )
        print(f'Space repository ready at: https://huggingface.co/spaces/{repo_id}')
    except Exception as e:
        print(f'Repo notice: {e}')

    folder_path = Path(__file__).resolve().parent
    print(f'Uploading all files from {folder_path} to {repo_id}...')
    try:
        api.upload_folder(
            folder_path=str(folder_path),
            repo_id=repo_id,
            repo_type='space',
            ignore_patterns=['__pycache__/*', '.git/*', '*.pyc', 'deploy.py']
        )
        print(f'DEPLOYMENT COMPLETE! Space is live at: https://huggingface.co/spaces/{repo_id}')
        return True
    except Exception as e:
        print(f'Upload failed: {e}')
        return False

if __name__ == '__main__':
    token = sys.argv[1] if len(sys.argv) > 1 else os.getenv('HF_TOKEN', '')
    if not token:
        print('Usage: python deploy.py HF_WRITE_TOKEN')
    else:
        deploy_space(token)
