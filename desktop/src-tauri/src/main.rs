#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    #[cfg(windows)]
    if tauri::webview_version().is_err() {
        let message: Vec<u16> = "화면을 표시하려면 Microsoft Edge WebView2 Runtime이 필요합니다.\n\n학교 PC 담당자에게 WebView2 Evergreen Runtime 설치를 요청해 주세요.\n설치 안내: https://developer.microsoft.com/microsoft-edge/webview2/\n\nWebView2 설치 후 이 앱을 다시 실행하세요."
            .encode_utf16().chain(Some(0)).collect();
        let title: Vec<u16> = "교원호봉획정도우미X슬교행".encode_utf16().chain(Some(0)).collect();
        unsafe {
            windows_sys::Win32::UI::WindowsAndMessaging::MessageBoxW(
                std::ptr::null_mut(), message.as_ptr(), title.as_ptr(),
                windows_sys::Win32::UI::WindowsAndMessaging::MB_OK
                    | windows_sys::Win32::UI::WindowsAndMessaging::MB_ICONERROR);
        }
        return;
    }
    hobong_desktop_lib::run();
}
