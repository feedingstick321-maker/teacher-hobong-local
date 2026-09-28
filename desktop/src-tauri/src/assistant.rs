use serde_json::{json, Value};
use std::fs;
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, State};

const GIB: u64 = 1024 * 1024 * 1024;

#[derive(Clone, Copy)]
struct Memory { total: u64, available: u64 }

fn memory() -> Option<Memory> {
    #[cfg(windows)] unsafe {
        use windows_sys::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};
        let mut data: MEMORYSTATUSEX = std::mem::zeroed();
        data.dwLength = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
        if GlobalMemoryStatusEx(&mut data) == 0 { return None; }
        Some(Memory { total: data.ullTotalPhys, available: data.ullAvailPhys })
    }
    #[cfg(not(windows))] { None }
}

fn memory_permission(value: Option<Memory>, resident: bool) -> Result<(), String> {
    let value = value.ok_or("메모리 상태를 확인하지 못해 AI 로딩을 하지 않습니다. 기본 규칙 기능은 사용할 수 있습니다.")?;
    if value.total < 15 * GIB {
        return Err("8GB급 PC에서는 4B 모델을 로딩하지 않습니다. 16GB 이상 PC를 권장하며 기본 규칙 기능은 계속 사용할 수 있습니다.".into());
    }
    let required = if resident { 2 * GIB } else { 8 * GIB };
    if value.available < required {
        return Err(format!("현재 가용 메모리가 {:.1}GiB로 부족합니다. {}GiB 이상 여유가 필요하며 기본 규칙 기능은 계속 사용할 수 있습니다.", value.available as f64 / GIB as f64, required/GIB));
    }
    Ok(())
}

struct OwnedEngine { child: Child, job: usize }
impl Drop for OwnedEngine {
    fn drop(&mut self) {
        #[cfg(windows)] unsafe { windows_sys::Win32::Foundation::CloseHandle(self.job as _); }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn launch(root: &PathBuf, work: &PathBuf) -> Result<(OwnedEngine, String), String> {
    use std::os::windows::process::CommandExt;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::JobObjects::*;
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    if port == 11434 { return Err("내부 엔진용 포트를 할당하지 못했습니다.".into()); }
    drop(listener);
    let runtime = root.join("runtime");
    fs::create_dir_all(work).map_err(|e| format!("AI 작업 폴더 생성 실패: {e}"))?;
    let mut command = Command::new(runtime.join("ollama.exe"));
    // Never use the read-only MSIX installation directory as a working/profile folder.
    command.arg("serve").current_dir(work)
        .env("USERPROFILE", work)
        .env("OLLAMA_HOST", format!("127.0.0.1:{port}"))
        .env("OLLAMA_MODELS", root.join("model-cache"))
        .env("CUDA_VISIBLE_DEVICES", "-1").env("OLLAMA_VULKAN", "0")
        .env("GGML_VK_VISIBLE_DEVICES", "-1").env("OLLAMA_NUM_PARALLEL", "1")
        .env("OLLAMA_MAX_LOADED_MODELS", "1").env("OLLAMA_KEEP_ALIVE", "-1")
        .env("OLLAMA_NO_CLOUD", "1").env("OLLAMA_NOPRUNE", "1")
        .env("OLLAMA_DEBUG", "0").env("OLLAMA_DEBUG_LOG_REQUESTS", "0")
        .env("OLLAMA_NOHISTORY", "1").env_remove("OLLAMA_ORIGINS")
        .env_remove("OLLAMA_LLM_LIBRARY").env_remove("OLLAMA_EXPERIMENT")
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
        .creation_flags(0x0800_0000);
    let mut child = command.spawn().map_err(|e| format!("동봉 CPU 엔진 실행 실패: {e}"))?;
    let job = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
    if job.is_null() { let _=child.kill(); let _=child.wait(); return Err("CPU 엔진의 자동 종료 보호를 만들지 못했습니다.".into()); }
    let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    let protected = unsafe { SetInformationJobObject(job, JobObjectExtendedLimitInformation,
        &limits as *const _ as _, std::mem::size_of_val(&limits) as u32) != 0
        && AssignProcessToJobObject(job, child.as_raw_handle()) != 0 };
    if !protected {
        unsafe { CloseHandle(job); } let _=child.kill(); let _=child.wait();
        return Err("CPU 엔진의 자동 종료 보호를 적용하지 못했습니다.".into());
    }
    Ok((OwnedEngine {child, job:job as usize}, format!("http://127.0.0.1:{port}")))
}

struct Inner {
    root: PathBuf, work: Option<PathBuf>, preferences: Option<PathBuf>, bundled: bool, auto_prepare: bool,
    phase: String, reason: String, engine: Option<OwnedEngine>, endpoint: String,
    preparing: bool, active: bool, generation: u64, resident_bytes: u64,
}

#[derive(Clone)]
pub struct Assistant(Arc<Mutex<Inner>>);
impl Assistant {
    pub fn new(app: &AppHandle) -> Self {
        let root = std::env::current_exe().ok().and_then(|p|p.parent().map(|p|p.to_path_buf())).unwrap_or_default();
        let bundled = root.join("runtime/ollama.exe").is_file()
            && root.join("model-cache/manifests/registry.ollama.ai/library/qwen3.5/4b").is_file();
        let preferences = app.path().app_config_dir().ok().map(|p|p.join("ai-preferences.json"));
        let work = app.path().app_local_data_dir().ok().map(|p|p.join("assistant"));
        let auto_prepare = preferences.as_ref().and_then(|p|fs::read_to_string(p).ok()).and_then(|s|serde_json::from_str::<Value>(&s).ok())
            .and_then(|v|v.get("auto_prepare").and_then(Value::as_bool)).unwrap_or(true);
        Self(Arc::new(Mutex::new(Inner {root,work,preferences,bundled,auto_prepare,
            phase:if bundled {"idle"}else{"not_available"}.into(),reason:String::new(),
            engine:None,endpoint:String::new(),preparing:false,active:false,generation:0,resident_bytes:0})))
    }
    pub fn shutdown(&self) {
        if let Ok(mut inner)=self.0.lock() {
            inner.generation+=1; inner.engine.take(); inner.endpoint.clear(); inner.resident_bytes=0;
            inner.phase="unloaded".into();
        }
    }
    fn status(&self) -> Value {
        let mut data=self.0.lock().unwrap(); let mem=memory();
        if data.phase=="ready" && data.engine.as_mut().is_none_or(|e| !matches!(e.child.try_wait(), Ok(None))) {
            data.engine.take();data.endpoint.clear();data.resident_bytes=0;
            data.phase="error".into();
            data.reason="AI 엔진이 종료되었습니다. AI 다시 준비해 보기를 누르세요. 기본 기능은 계속 사용할 수 있습니다.".into();
        }
        json!({"bundled":data.bundled,"phase":data.phase,"reason":data.reason,
            "auto_prepare":data.auto_prepare,"active":data.active,"device":"cpu",
            "total_bytes":mem.map(|v|v.total),"available_bytes":mem.map(|v|v.available),
            "resident_bytes":data.resident_bytes,"process_id":data.engine.as_ref().map(|e|e.child.id())})
    }
}

async fn prepare(app: AppHandle, manager: Assistant, automatic: bool) {
    let (root,work,generation)={
        let mut inner=manager.0.lock().unwrap();
        if !inner.bundled || inner.preparing || inner.active || inner.phase=="ready" { return; }
        if automatic && !inner.auto_prepare { inner.phase="skipped".into();inner.reason="AI 자동 준비를 껐습니다. 기본 규칙 기능으로 시작합니다.".into();return; }
        if let Err(reason)=memory_permission(memory(),false) { inner.phase="skipped".into();inner.reason=reason;return; }
        let Some(work)=inner.work.clone() else {inner.phase="error".into();inner.reason="AI 사용자 작업 폴더를 찾지 못했습니다.".into();return;};
        inner.preparing=true;inner.phase="loading".into();inner.reason="CPU 모델을 준비하고 있습니다. 파일 선택과 기본 입력은 계속할 수 있습니다.".into();
        inner.generation+=1;(inner.root.clone(),work,inner.generation)
    };
    let result: Result<Value,String>=async {
        let (engine,endpoint)=launch(&root,&work)?;
        {
            let mut inner=manager.0.lock().unwrap();
            if inner.generation!=generation { return Err("모델 준비가 취소되었습니다.".into()); }
            inner.engine=Some(engine);inner.endpoint=endpoint.clone();
        }
        let address=endpoint.trim_start_matches("http://").to_string();
        let deadline=Instant::now()+Duration::from_secs(20);
        loop {
            {let mut inner=manager.0.lock().unwrap();
            if inner.generation!=generation {return Err("모델 준비가 취소되었습니다.".into());}
            if inner.engine.as_mut().and_then(|e|e.child.try_wait().ok()).flatten().is_some(){return Err("CPU 엔진이 시작 중 종료되었습니다.".into());}}
            if TcpStream::connect(&address).is_ok(){break;}
            if Instant::now()>=deadline{return Err("CPU 엔진 시작 시간이 초과되었습니다.".into());}
            tauri::async_runtime::spawn_blocking(||std::thread::sleep(Duration::from_millis(100))).await.map_err(|e|e.to_string())?;
        }
        let temp=tempfile::tempdir().map_err(|e|e.to_string())?;
        let output=temp.path().join("warmup.json");
        crate::run_sidecar(&app,vec!["warmup-llm".into(),"--endpoint".into(),endpoint,"--output".into(),crate::path_text(&output)]).await?;
        serde_json::from_str(&fs::read_to_string(output).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
    }.await;
    let mut inner=manager.0.lock().unwrap();
    if inner.generation!=generation{return;}
    inner.preparing=false;
    match result {
        Ok(value)=>{inner.phase="ready".into();inner.reason="4B CPU 모델 준비 완료. 참고 후보는 자동 적용되지 않습니다.".into();inner.resident_bytes=value["resident_bytes"].as_u64().unwrap_or(0);}
        Err(error)=>{inner.engine.take();inner.endpoint.clear();inner.phase="error".into();inner.reason=format!("AI 준비 실패: {error} 기본 규칙 기능은 사용할 수 있습니다.");}
    }
}

pub fn startup(app: AppHandle, manager: Assistant) { tauri::async_runtime::spawn(prepare(app,manager,true)); }

#[tauri::command]
pub fn assistant_status(manager: State<'_,Assistant>) -> Value { manager.status() }

#[tauri::command]
pub fn prepare_assistant(app: AppHandle, manager: State<'_,Assistant>) -> Value {
    let manager=manager.inner().clone();let status=manager.status();
    tauri::async_runtime::spawn(prepare(app,manager,false));status
}

#[tauri::command]
pub fn set_assistant_auto(enabled: bool, manager: State<'_,Assistant>) -> Result<Value,String> {
    let mut inner=manager.0.lock().unwrap();
    let preferences=inner.preferences.as_ref().ok_or("사용자 설정 폴더를 찾지 못했습니다. 설치 폴더에는 저장하지 않습니다.")?;
    let parent=preferences.parent().ok_or("설정 폴더를 찾지 못했습니다.")?;
    fs::create_dir_all(parent).map_err(|e|e.to_string())?;
    fs::write(preferences,serde_json::to_vec(&json!({"auto_prepare":enabled})).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
    inner.auto_prepare=enabled;drop(inner);Ok(manager.status())
}

#[tauri::command]
pub fn unload_assistant(manager: State<'_,Assistant>) -> Result<Value,String> {
    let mut inner=manager.0.lock().unwrap();
    if inner.active {return Err("AI 추천이 끝난 뒤 모델을 내려 주세요.".into());}
    inner.generation+=1;inner.engine.take();inner.endpoint.clear();inner.resident_bytes=0;
    inner.phase="unloaded".into();inner.preparing=false;
    inner.reason="모델을 내려 메모리를 반환했습니다. 이 실행에서는 자동으로 다시 로딩하지 않습니다.".into();
    drop(inner);Ok(manager.status())
}

#[tauri::command]
pub async fn recommend_with_assistant(app: AppHandle, manager: State<'_,Assistant>, organization: String, position: String, raw_text: String, verified_facts: Option<Value>) -> Result<Value,String> {
    let manager=manager.inner().clone();
    let endpoint={let mut inner=manager.0.lock().unwrap();
        if inner.phase!="ready" {return Err("AI 모델이 아직 준비되지 않았습니다. 상태 안내를 확인하거나 기본 규칙 추천을 사용하세요.".into());}
        if inner.active{return Err("다른 AI 참고 추천이 진행 중입니다.".into());}
        memory_permission(memory(),true)?;inner.active=true;inner.endpoint.clone()};
    let result: Result<Value,String>=async {
        let temp=tempfile::tempdir().map_err(|e|e.to_string())?;
        let request=temp.path().join("request.json");let output=temp.path().join("candidate.json");
        fs::write(&request,serde_json::to_vec(&json!({"organization":organization,"position":position,"raw_text":raw_text,"verified_facts":verified_facts})).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
        crate::run_sidecar(&app,vec!["recommend-llm".into(),"--endpoint".into(),endpoint,"--request".into(),crate::path_text(&request),"--output".into(),crate::path_text(&output)]).await?;
        serde_json::from_str(&fs::read_to_string(output).map_err(|e|e.to_string())?).map_err(|e|e.to_string())
    }.await;
    manager.0.lock().unwrap().active=false;result
}

#[cfg(test)] mod tests {
    use super::*;
    #[test] fn loading_memory_gate() {
        assert!(memory_permission(Some(Memory{total:8*GIB,available:6*GIB}),false).is_err());
        assert!(memory_permission(Some(Memory{total:16*GIB,available:2*GIB}),false).is_err());
        assert!(memory_permission(Some(Memory{total:16*GIB,available:9*GIB}),false).is_ok());
        assert!(memory_permission(Some(Memory{total:64*GIB,available:32*GIB}),false).is_ok());
        assert!(memory_permission(None,false).is_err());
    }
    #[test] fn resident_memory_gate() {
        assert!(memory_permission(Some(Memory{total:16*GIB,available:3*GIB}),true).is_ok());
        assert!(memory_permission(Some(Memory{total:16*GIB,available:GIB}),true).is_err());
    }
}
