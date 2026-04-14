const generateButton = document.querySelector("#generateButton");
const sendButton = document.querySelector("#sendButton");
const preview = document.querySelector("#preview");
const status = document.querySelector("#status");

function setStatus(message, type = "") {
  status.textContent = message;
  status.className = `status ${type}`.trim();
}

generateButton.addEventListener("click", async () => {
  setStatus("더미데이터 생성 중...");

  try {
    const response = await fetch("/dummy-statement");
    const statement = await response.json();

    preview.value = JSON.stringify(statement, null, 2);
    sendButton.disabled = false;
    setStatus("더미데이터가 준비됐습니다.", "ok");
  } catch (error) {
    setStatus(`생성 실패: ${error.message}`, "error");
  }
});

sendButton.addEventListener("click", async () => {
  setStatus("Receiver로 전송 중...");
  sendButton.disabled = true;

  try {
    const statement = JSON.parse(preview.value);
    const response = await fetch("/send-statement", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(statement),
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "전송 요청이 실패했습니다.");
    }

    setStatus(`전송 완료: Receiver 응답 ${response.status}`, "ok");
  } catch (error) {
    setStatus(`전송 실패: ${error.message}`, "error");
  } finally {
    sendButton.disabled = false;
  }
});
