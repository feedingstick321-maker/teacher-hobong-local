# 제3자 소프트웨어 및 모델 고지

교원호봉획정도우미X슬교행 4B CPU 0.1.15 검수본의 구성요소에 대한 고지입니다.
제3자 구성요소의 저작권과 상표는 각각의 권리자에게 있습니다. 원저작자의 공식 제품이나 보증으로 표시하지 않습니다.

## Ollama CPU 런타임

- 버전: Ollama 0.34.4, Windows AMD64.
- 저작권: Copyright (c) Ollama.
- 라이선스: MIT. 원문: `licenses/Ollama-MIT.txt`.
- 공식 출처: https://github.com/ollama/ollama/blob/v0.34.4/LICENSE
- 포함 위치: `runtime/ollama.exe`, `runtime/lib/ollama/`.
- 원본 실행파일과 CPU 라이브러리를 수정하지 않고 동봉합니다. GPU 런타임 디렉터리
  `cuda_v12`, `cuda_v13`, `rocm_v7_1`, `vulkan`은 포함하지 않습니다.
  별도 Ollama GUI, 설치 제거 도구, 전역 서비스 등록은 포함하지 않습니다.
- 모델 양자화 실행파일 `llama-quantize.exe`는 배포하지 않습니다. CPU 추론 서버와 DLL 및
  원본 배포의 최상위 라이선스·고지 파일은 보존합니다.

`runtime/lib/ollama/`의 다음 라이선스·고지 원문도 함께 보존합니다:

`CPP_HTTPLIB_LICENSE`, `CUDNN_LICENSE.txt`, `CUTLASS_LICENSE.txt`, `DLFCN_WIN32_COPYING`,
`DLPACK_LICENSE`, `FMT_LICENSE`, `GO_LICENSE`, `JSON_LICENSE.MIT`, `LLAMA_CPP_LICENSE`,
`LLAMA_CPP_VENDORS_LICENSE`, `MLX_C_LICENSE`, `MLX_LICENSE`, `NVTX3_LICENSE.txt`,
`PICOJSON_LICENSE`, `XGRAMMAR_LICENSE`, `XGRAMMAR_NOTICE`.

상기 라이선스 파일 중 GPU/다른 플랫폼 구성요소 관련 원문이 남아 있어도 해당 GPU 런타임이
동봉되었다는 의미는 아닙니다. 세부 조건 및 저작권 고지는 각각의 원문을 확인해 주세요.

## Qwen3.5-4B 모델

- 모델: Ollama `qwen3.5:4b`, GGUF Q4_K_M, 원모델 Qwen/Qwen3.5-4B.
- 공식 저작권 고지: Copyright 2026 Alibaba Cloud.
- 라이선스: Apache License, Version 2.0.
- 공식 모델 저장소 및 라이선스: https://huggingface.co/Qwen/Qwen3.5-4B/blob/main/LICENSE
- 공식 라이선스 원문: `licenses/Qwen3.5-4B-APACHE-2.0.txt`.
- Ollama 모델 manifest가 참조하는 라이선스 원문: `licenses/Qwen3.5-4B-Ollama-License.txt`.
  두 원문 모두 보존하며 공식 라이선스에는 Alibaba Cloud의 명시적인 저작권 고지가 있습니다.
- 포함 위치: `model-cache/manifests/registry.ollama.ai/library/qwen3.5/4b`와 참조 blob 네 개.
- 모델 blob SHA-256:
  `81fb60c7daa80fc1123380b98970b320ae233409f0f71a72ed7b9b0d62f40490`
  (3,389,971,840 bytes).
- 모델·manifest·config·params·라이선스 blob은 원본을 수정하지 않고 복사했습니다.
  이 배포 작업에서 추가 학습이나 모델 재양자화를 수행하지 않았습니다.

AI 출력은 사실·법령·경력을 확정하는 자료가 아니며 사람이 원문과 근거를 확인해야 합니다.

## 설치 프로그램

Store용 MSIX는 Windows SDK MakeAppx로 생성합니다. 아래 Inno Setup 고지는 이전 직접 설치본 제작 도구에 해당합니다.

설치 EXE는 Inno Setup 6.7.3으로 제작하도록 구성했습니다.
Inno Setup 저작권과 라이선스 원문은 `licenses/Inno-Setup-License.txt`에 보존합니다.
공식 출처: https://jrsoftware.org/ 및 https://jrsoftware.org/files/is/license.txt

빌드에만 사용하는 Inno Unpacker 도구는 이 앱 배포본에 포함하지 않습니다.

## Python / Rust 구성요소

`licenses/python/`과 `licenses/rust/`에 설치된 의존성의 원문 고지를 보존했습니다.
버전과 수집 목록은 `licenses/component-inventory.json`에 있습니다. Rust 목록은 Windows 빌드의
잠금 파일 의존성을 포함하므로 빌드 도구용 항목도 포함될 수 있습니다.

배포 wheel에 원문이 없는 RapidOCR 3.9.1, ANTLR 4.9.3, FlatBuffers 25.12.19는
각 공식 저장소의 해당 버전 라이선스를 보충했습니다. 출처와 SHA-256은 목록에 기록했습니다.
CPython은 `licenses/CPython-LICENSE.txt`, PyInstaller 부트로더는
`licenses/python/pyinstaller-*/`의 원문과 부트로더 예외 조항을 참조하세요.
PP-OCRv5 계열 OCR 모델의 상위 PaddleOCR 프로젝트 고지는
`licenses/PaddleOCR-APACHE-2.0.txt`에 포함합니다.

PDF 읽기 엔진 PyMuPDF 1.28.0은 AGPL 또는 Artifex 상용 라이선스입니다.
배포 wheel의 `licenses/python/pymupdf-1.28.0/00-COPYING`은 이중 라이선스의
짧은 표시일 뿐 AGPL 전문이 아닙니다. GNU Affero General Public License 3.0
전문은 `licenses/AGPL-3.0-only.txt`에 보존했습니다.
이 배포판은 상용 Artifex 라이선스를 주장하지 않으며, 앱 소스 코드를
AGPL-3.0-only로 공개합니다. 해당 버전의 소스와 빌드 절차는 아래에서
무료로 내려받을 수 있습니다.

https://github.com/feedingstick321-maker/teacher-hobong-local

소스 저장소에는 개인정보가 포함된 입력 증명서, 실물 테스트 자료,
설치된 운영체제 런타임 및 대용량 제3자 모델 가중치를 넣지 않습니다.
각 제3자 구성요소의 별도 라이선스와 모델 출처는 이 문서 및 동봉된
`licenses/` 원문을 따릅니다. 이 고지는 법률 자문이나 권리자의 보증이 아닙니다.
