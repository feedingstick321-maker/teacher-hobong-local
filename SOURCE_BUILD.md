# 1.0.15.0 공개 소스와 재구성

이 저장소는 Microsoft Store용 `교원호봉획정도우미X슬교행` 1.0.15.0의
앱 코드, CPU OCR 모델, 데이터, 잠금 파일, 빌드·패키징 스크립트 및 라이선스
고지를 제공합니다. 사용자가 업로드한 실물 증명서와 개인정보는 포함하지 않습니다.
앱 코드는 AGPL-3.0-only입니다. Python/Rust/JavaScript 패키지와 OCR/언어
모델에는 각각의 라이선스가 적용됩니다(`THIRD-PARTY-NOTICES.md`, `licenses/`).

## Windows 빌드 환경

- Windows 10/11 x64, Python 3.11, Rust MSVC 도구 체인, Node.js/npm, Windows SDK
  MakeAppx, WebView2. 잠금 파일: `desktop/package-lock.json`,
  `desktop/src-tauri/Cargo.lock`.
- Python 의존성: `requirements.txt`. PyInstaller로 사이드카를 묶습니다.
- Tauri 2 정식 빌드(`npm run tauri build`)로 내장 웹 화면을 포함합니다.
  단순 `cargo build --release` 결과는 Store 배포용으로 사용하지 마세요.
- 아래 명령은 저장소 루트의 PowerShell에서 실행합니다. 사용자 문서·출력 파일은
  MSIX 설치 폴더가 아니라 사용자 데이터/지정 출력 폴더에 저장합니다.

```powershell
py -3.11 -m venv .venv-cpu
.venv-cpu\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.venv-cpu\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging/certocr-sidecar.spec
New-Item -ItemType Directory desktop/src-tauri/binaries -Force | Out-Null
Copy-Item dist/certocr-sidecar.exe desktop/src-tauri/binaries/certocr-sidecar-x86_64-pc-windows-msvc.exe
Push-Location desktop
npm ci
npm run tauri build
Pop-Location
```

Tauri 빌드 산출물의 `hobong-desktop.exe`와 사이드카를
`school-dist/portable-0.1.15-4b/`에 놓고, 아래 제3자 런타임/모델 및
라이선스 원문을 같은 폴더에 준비합니다. `packaging/Build-Store.ps1`은
이 폴더에서 **명시된 배포 파일만** 가져와 Store용 unsigned MSIX를 만듭니다.

```powershell
./packaging/Build-Store.ps1
```

스크립트는 Windows SDK MakeAppx 기본 검증을 켠 채 패키징하고 다시 풀어
모든 포함 파일의 SHA-256을 비교합니다. Store용 MSIX 생성은 서명·설치·WACK·
Store 업로드·심사 통과를 뜻하지 않습니다. 버전/Identity는
`packaging/store-identity.json`에 있으며 업데이트 제출 전 Partner Center의
앱별 값과 기존 제출 버전을 다시 확인해야 합니다.

## 별도 내려받는 제3자 실행 파일과 4B 모델

대용량 가중치와 Ollama 실행 바이너리는 GitHub 소스 저장소에 복제하지 않습니다.
해당 버전의 공식 배포물과 라이선스를 받아 직접 준비할 수 있습니다.

- [Ollama v0.34.4 공식 릴리스](https://github.com/ollama/ollama/releases/tag/v0.34.4):
  Windows AMD64의 `ollama.exe`와 `lib/ollama` 중 CPU 실행에 필요한 DLL·원문
  라이선스만 `runtime/`에 둡니다. CUDA/ROCm/Vulkan 디렉터리는 동봉하지
  않습니다. `THIRD-PARTY-NOTICES.md`에 원본 고지 목록이 있습니다.
- [Qwen3.5-4B 원모델](https://huggingface.co/Qwen/Qwen3.5-4B),
  [Ollama qwen3.5:4b 배포](https://ollama.com/library/qwen3.5:4b):
  `ollama pull qwen3.5:4b` 후 Ollama 모델 캐시의 해당 manifest와 참조 blob을
  `model-cache/`에 배치합니다. **이 배포판에 사용한** Q4_K_M 가중치는
  3,389,971,840바이트, SHA-256
  `81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490`;
  manifest digest는
  `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`
  입니다. 모델 태그는 갱신될 수 있으므로 해시가 다르면 동일 배포 모델이라고
  주장하지 말고 해당 버전의 정확한 가중치를 확보해야 합니다.

원본 OCR PP-OCRv5 모델은 `data/models/`에 포함되어 있습니다. 빌드에 사용한
OCR 모델 및 제3자 패키지의 원문 고지는 `licenses/`에 있습니다.
소스의 기능적 재구성과 과거 MSIX의 바이트 단위 재현은 다릅니다. 동일한
도구 버전·입력물·빌드 환경이 없으면 결과 해시가 달라질 수 있습니다.
