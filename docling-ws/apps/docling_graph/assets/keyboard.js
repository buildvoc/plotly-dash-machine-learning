document.addEventListener("keydown", function (e) {
  const tag = e.target && e.target.tagName ? e.target.tagName.toLowerCase() : "";
  console.log("[docling-graph] keydown:", e.key, "target:", tag);

  // Ignore typing in form fields
  if (tag === "input" || tag === "textarea" || e.target.isContentEditable) return;

  function click(id) {
    const el = document.getElementById(id);
    console.log("[docling-graph] click lookup:", id, "found:", !!el);
    if (el) el.click();
  }

  if (e.key === "+" || e.key === "=") {
    e.preventDefault();
    click("zoom-in-btn");
  } else if (e.key === "-" || e.key === "_") {
    e.preventDefault();
    click("zoom-out-btn");
  } else if (e.key === "0") {
    e.preventDefault();
    click("zoom-reset-btn");
  }
});
