use base64::Engine;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::AppHandle;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
mod assistant;

fn path_text(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

async fn run_sidecar(app: &AppHandle, args: Vec<String>) -> Result<(), String> {
    let command = app
        .shell()
        .sidecar("certocr-sidecar")
        .map_err(|error| format!("문서 엔진을 찾을 수 없습니다: {error}"))?
        .args(args);
    let output = command
        .output()
        .await
        .map_err(|error| format!("문서 엔진 실행 실패: {error}"))?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let detail = detail.lines().rev().find_map(|line| {
            serde_json::from_str::<Value>(line).ok()
                .and_then(|value| value.get("error").and_then(Value::as_str).map(str::to_owned))
        }).unwrap_or(detail);
        return Err(if detail.is_empty() {
            "문서 엔진이 비정상 종료되었습니다.".to_string()
        } else {
            detail
        });
    }
    Ok(())
}

async fn extract_with_command(
    app: AppHandle,
    base64: String,
    mime_type: String,
    command: &str,
) -> Result<Value, String> {
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(base64)
        .map_err(|error| format!("파일 데이터가 올바르지 않습니다: {error}"))?;
    if bytes.is_empty() {
        return Err("빈 파일입니다.".to_string());
    }
    if bytes.len() > 50 * 1024 * 1024 {
        return Err("파일은 최대 50MB까지 처리할 수 있습니다.".to_string());
    }

    let temp = tempfile::tempdir().map_err(|error| format!("임시 폴더 생성 실패: {error}"))?;
    let input = temp.path().join("document.bin");
    let output = temp.path().join("result.json");
    fs::write(&input, bytes).map_err(|error| format!("임시 파일 저장 실패: {error}"))?;
    run_sidecar(
        &app,
        vec![
            command.into(),
            "--input".into(),
            path_text(&input),
            "--output".into(),
            path_text(&output),
            "--mime".into(),
            mime_type,
        ],
    )
    .await?;
    let text =
        fs::read_to_string(&output).map_err(|error| format!("분석 결과 읽기 실패: {error}"))?;
    serde_json::from_str(&text).map_err(|error| format!("분석 결과 형식 오류: {error}"))
}

#[tauri::command]
async fn extract_document(
    app: AppHandle,
    base64: String,
    mime_type: String,
) -> Result<Value, String> {
    extract_with_command(app, base64, mime_type, "extract").await
}

#[tauri::command]
async fn extract_salary_document(
    app: AppHandle,
    base64: String,
    mime_type: String,
) -> Result<Value, String> {
    extract_with_command(app, base64, mime_type, "extract-salary").await
}

#[tauri::command]
async fn recommend_career_type(
    app: AppHandle,
    organization: String,
    position: String,
    weekly_hours: Option<String>,
    raw_text: String,
    verified_facts: Option<Value>,
) -> Result<Value, String> {
    let temp = tempfile::tempdir().map_err(|error| format!("임시 폴더 생성 실패: {error}"))?;
    let request = temp.path().join("career.json");
    let output = temp.path().join("recommendation.json");
    let payload = serde_json::json!({
        "organization": organization,
        "position": position,
        "weekly_hours": weekly_hours,
        "raw_text": raw_text,
        "verified_facts": verified_facts,
    });
    fs::write(&request, serde_json::to_vec(&payload).map_err(|error| error.to_string())?)
        .map_err(|error| format!("추천 요청 저장 실패: {error}"))?;
    run_sidecar(
        &app,
        vec![
            "recommend-career".into(),
            "--request".into(),
            path_text(&request),
            "--output".into(),
            path_text(&output),
        ],
    )
    .await?;
    let text = fs::read_to_string(&output).map_err(|error| format!("추천 결과 읽기 실패: {error}"))?;
    serde_json::from_str(&text).map_err(|error| format!("추천 결과 형식 오류: {error}"))
}

fn valid_output_path(path: &Path, kind: &str) -> Result<PathBuf, String> {
    if !path.is_absolute() {
        return Err("저장 경로는 절대 경로여야 합니다.".to_string());
    }
    let expected = if kind == "excel" {
        "xlsx"
    } else if kind == "pdf" {
        "pdf"
    } else {
        return Err("지원하지 않는 파일 형식입니다.".to_string());
    };
    if path
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.eq_ignore_ascii_case(expected))
        != Some(true)
    {
        return Err(format!("저장 파일의 확장자는 .{expected}여야 합니다."));
    }
    Ok(path.to_path_buf())
}

#[tauri::command]
async fn export_document(
    app: AppHandle,
    kind: String,
    payload: Value,
    output_path: String,
) -> Result<String, String> {
    let target = valid_output_path(Path::new(&output_path), &kind)?;
    let temp = tempfile::tempdir().map_err(|error| format!("임시 폴더 생성 실패: {error}"))?;
    let request = temp.path().join("request.json");
    fs::write(
        &request,
        serde_json::to_vec(&payload).map_err(|error| format!("조서 데이터 변환 실패: {error}"))?,
    )
    .map_err(|error| format!("임시 요청 저장 실패: {error}"))?;
    let command = if kind == "excel" {
        "export-excel"
    } else {
        "export-pdf"
    };
    run_sidecar(
        &app,
        vec![
            command.into(),
            "--request".into(),
            path_text(&request),
            "--output".into(),
            path_text(&target),
        ],
    )
    .await?;
    if !target.is_file() || target.metadata().map_err(|error| error.to_string())?.len() == 0 {
        return Err("생성된 파일을 확인할 수 없습니다.".to_string());
    }
    Ok(path_text(&target))
}

#[tauri::command]
fn open_brand_channel(app: AppHandle) -> Result<(), String> {
    #[allow(deprecated)]
    app.shell()
        .open("https://www.youtube.com/@wise-gyohaeng", None)
        .map_err(|error| format!("기본 브라우저 열기 실패: {error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let manager = assistant::Assistant::new(app.handle());
            app.manage(manager.clone());
            assistant::startup(app.handle().clone(), manager);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            extract_document,
            extract_salary_document,
            recommend_career_type,
            export_document,
            open_brand_channel,
            assistant::assistant_status,
            assistant::prepare_assistant,
            assistant::set_assistant_auto,
            assistant::unload_assistant,
            assistant::recommend_with_assistant
        ])
        .build(tauri::generate_context!())
        .expect("호봉획정 도우미 실행 실패")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                app.state::<assistant::Assistant>().shutdown();
            }
        });
}
