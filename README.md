# 교원 호봉 획정·재획정기

이 저장소는 Microsoft Store용 `교원호봉획정도우미X슬교행` 1.0.15.0의
공개 소스입니다. 앱 코드는 [GNU AGPL-3.0-only](LICENSE)로 배포합니다.
제3자 라이브러리·OCR/언어 모델·일러스트의 권리는 각각의 원저작자에게 있으며,
라이선스와 출처는 [제3자 고지](THIRD-PARTY-NOTICES.md)를 확인하세요.
실제 증명서·개인정보·서명키·비밀키는 저장소에 포함하지 않습니다.

소스와 동일한 Store 패키지의 재구성 방법 및 모델 출처는
[SOURCE_BUILD.md](SOURCE_BUILD.md)를 참조하세요. 이 공개 저장소의 소스는
누구나 열람·수정·재배포할 수 있으나, 원본 호봉 판단 결과의 정확성을 보증하지 않습니다.

경력증명서·교원자격증·졸업증명서·학위증명서와 기존 호봉자료를 OCR로 읽고, 교원 호봉 획정·재획정 검토를 지원하는 Windows 데스크톱 프로그램입니다.

- 문서 OCR, 경력 구조화, 환산율 추천, Excel·PDF 출력까지 PC 내부에서 처리
- 외부 API 호출 및 문서 업로드 없음
- `CPUExecutionProvider` 고정: GPU가 없는 학교 PC에서도 실행
- Tauri 2 데스크톱 UI + Python CPU 사이드카
- 법령 스냅샷과 결정형 규칙 엔진으로 추천 근거와 필수 확인사항 표시

> 이 프로그램은 담당자의 검토를 돕는 도구입니다. 최종 호봉 결정은 원본 증빙과 시행일 현재의 법령·예규를 담당자가 다시 확인해야 합니다.

## 주요 기능

1. 경력증명서에서 근무기간, 기관, 직종, 주당시수 후보 추출
2. 교원자격증·졸업증명서·학위증명서 자동 분류와 학력·자격 정보 추출
3. 호봉획정표·재획정표·경력기간 합산신청서·시간강사 환산표 가져오기
4. 중복 경력 병합, 날짜 충돌과 저신뢰 항목의 검토 큐 표시
5. 공·사립 여부, 임면보고, 자격-학교급 일치 여부 등에 따른 경력환산율 후보 제시
6. 검토 결과를 호봉 조서 Excel 및 PDF로 출력

## 로컬 처리 보장

학교 배포 진입점은 환경변수와 무관하게 CPU만 사용합니다. 실행 중인 문서와 OCR 결과는 외부 생성형 AI, Cloud Run 또는 제3자 API로 전송하지 않습니다. 인터넷이 끊긴 환경에서도 설치 후 OCR·계산·출력이 가능합니다.

상태 확인 응답에는 다음 메타데이터가 포함됩니다.

```json
{
  "device": "cpu",
  "provider": "CPUExecutionProvider",
  "external_api_used": false
}
```

## 지원 환경

- Windows 10/11 x64
- Python 3.11
- RapidOCR 3.9.1 + PP-OCRv5 Korean
- ONNX Runtime CPU 1.23.2
- Tauri 2 / WebView2

로컬 OCR 모델은 `data/models/`에 포함합니다.

## 개발 환경 실행

```powershell
py -3.11 -m venv .venv-cpu
.venv-cpu\Scripts\python.exe -m pip install -r requirements.txt
.venv-cpu\Scripts\python.exe scripts\serve_hobong.py
```

브라우저에서 `http://127.0.0.1:8765/hobong.html`을 엽니다.

데스크톱 개발 실행:

```powershell
cd desktop
npm ci
npm run tauri dev
```

## 테스트

```powershell
.venv-cpu\Scripts\python.exe -m unittest discover -s tests -v
.venv-cpu\Scripts\python.exe -m certocr.degrade.selftest
node desktop\scripts\check-frontend.mjs
cd desktop\src-tauri
cargo check
```

실물 증명서와 정답 데이터는 개인정보 보호를 위해 저장소에서 제외합니다. 공개 저장소에는 소스, 로컬 OCR 모델, 합성 테스트 및 법령 기준만 포함합니다.

## 패키징

1. `packaging/certocr-sidecar.spec`로 CPU 사이드카를 빌드합니다.
2. 결과 실행 파일을 `desktop/src-tauri/binaries/certocr-sidecar-x86_64-pc-windows-msvc.exe`에 배치합니다.
3. `desktop`에서 `npm run tauri build`를 실행합니다.

NSIS 설치는 `currentUser` 방식이라 일반적인 학교 PC에서 관리자 권한 없이 설치할 수 있습니다. 빌드 산출물과 설치 파일은 Git 이력에 포함하지 않습니다.

## 법령 기준

현재 내장 규칙의 기준일은 2026-07-12입니다. 주요 근거와 구현 범위는 [LEGAL_BASIS.md](LEGAL_BASIS.md)에서 확인할 수 있습니다.
