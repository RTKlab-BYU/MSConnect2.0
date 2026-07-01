const filters = document.getElementById("queue-filters");
if (filters) {
  filters.querySelectorAll("select").forEach((el) => {
    el.addEventListener("change", () => filters.submit());
  });
}
