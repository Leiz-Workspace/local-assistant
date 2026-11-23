/** Exchange one ephemeral pairing fragment for an HttpOnly same-origin session. */
async function pairSession() {
    const code = window.location.hash.slice(1);
    window.history.replaceState(null, "", "/pair/");
    try {
        const response = await fetch("/ui/pairings", {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-Harness-UI": "1"},
            body: JSON.stringify({code})
        });
        if (!response.ok) throw new Error("pairing_failed");
        console.info("harness_session_paired");
        window.location.replace("/");
    } catch {
        console.warn("harness_session_pairing_failed");
        document.getElementById("status").textContent = "Phiên kết nối không hợp lệ hoặc đã hết hạn. Hãy chạy lại aevra ui open hoặc aevra desktop.";
    }
}
pairSession();
