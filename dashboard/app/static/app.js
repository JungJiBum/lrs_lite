const rawDialog = document.querySelector("#rawDialog");
const rawPreview = document.querySelector("#rawPreview");
const closeRawDialog = document.querySelector("#closeRawDialog");

document.querySelectorAll(".raw-button").forEach((button) => {
  button.addEventListener("click", () => {
    const rawSource = document.querySelector(`#${button.dataset.rawId}`);
    const payload = JSON.parse(rawSource.textContent);

    rawPreview.textContent = JSON.stringify(payload, null, 2);
    rawDialog.showModal();
  });
});

closeRawDialog.addEventListener("click", () => {
  rawDialog.close();
});

rawDialog.addEventListener("click", (event) => {
  if (event.target === rawDialog) {
    rawDialog.close();
  }
});
