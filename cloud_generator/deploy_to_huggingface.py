import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLOUD_DIR = Path(__file__).resolve().parent

def deploy():
    print("\n=======================================================")
    print("  🚀 1-Click Hugging Face Space Cloud Deployment")
    print("  Deploy your Video Factory to 24/7 Free Cloud Hosting")
    print("=======================================================\n")
    
    hf_token = os.getenv("HF_TOKEN") or input("Enter your free Hugging Face User Access Token (hf_...): ").strip()
    if not hf_token:
        print("Error: Hugging Face token is required. Get one at https://huggingface.co/settings/tokens")
        return
        
    space_name = input("Enter your Space Name (e.g. ai-video-factory): ").strip() or "ai-video-factory"
    username = input("Enter your Hugging Face Username: ").strip()
    if not username:
        print("Error: Username is required.")
        return
        
    repo_id = f"{username}/{space_name}"
    print(f"\nTarget Space: https://huggingface.co/spaces/{repo_id}")
    
    # Create staging folder for upload
    stage_dir = CLOUD_DIR / "staging_hf"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy essential cloud files
    cloud_files = (
        "Dockerfile", "requirements.txt", "README.md", "server.py", "config.py", 
        "pipeline.py", "prompt_engine.py", "voice_engine.py", "video_compiler.py", 
        "image_router.py", "facebook_publisher.py", "bulk_scheduler.py", 
        "self_healing.py", "cloud_storage.py", "notifier.py", "cloud_settings.json"
    )
    for item in cloud_files:
        src = CLOUD_DIR / item
        if src.exists():
            shutil.copy2(str(src), str(stage_dir / item))
            
    # Copy subdirectories
    for d in ("image_engines", "web"):
        src = CLOUD_DIR / d
        if src.exists():
            shutil.copytree(str(src), str(stage_dir / d))
            
    # Copy reference system and assets
    ref_sys = PROJECT_ROOT / "reference_system"
    if ref_sys.exists():
        shutil.copytree(str(ref_sys), str(stage_dir / "reference_system"))
        
    art_prompts = PROJECT_ROOT / "artwork_prompts.py"
    if art_prompts.exists():
        shutil.copy2(str(art_prompts), str(stage_dir / "artwork_prompts.py"))
        
    # Copy assets (overlays, music, reference voice, fonts)
    assets_dest = stage_dir / "assets"
    assets_dest.mkdir(parents=True, exist_ok=True)
    
    for sub in ("overlays", "Whispr Bg music", "reference_voice", "fonts"):
        sub_src = PROJECT_ROOT / "assets" / sub
        if sub_src.exists():
            shutil.copytree(str(sub_src), str(assets_dest / sub))
            
    print("Staging bundle prepared successfully.")
    
    # Push via huggingface_hub or git
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=hf_token)
        print(f"Creating Space {repo_id} (if not exists)...")
        api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
        print("Uploading files to Hugging Face Cloud Space...")
        api.upload_folder(
            folder_path=str(stage_dir),
            repo_id=repo_id,
            repo_type="space"
        )
        print(f"\n=======================================================")
        print(f"  🎉 SUCCESS! Your Studio is now LIVE in the Cloud!")
        print(f"  URL: https://huggingface.co/spaces/{repo_id}")
        print(f"  Your local PC can now be shut down anytime.")
        print(f"=======================================================\n")
    except ImportError:
        print("\nNote: Install huggingface_hub for automatic upload:")
        print("  pip install huggingface_hub")
        print(f"Or create a Space manually at https://huggingface.co/new-space (choose Docker) and push the files from:\n  {stage_dir}")
    except Exception as e:
        print(f"Upload error: {e}")
        print(f"You can also manually upload the files from:\n  {stage_dir}")

if __name__ == "__main__":
    deploy()
