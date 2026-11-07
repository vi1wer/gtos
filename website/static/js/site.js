(() => {
  const nav = document.querySelector("[data-nav]");
  const toggle = document.querySelector("[data-nav-toggle]");

  const onScroll = () => {
    if (!nav) return;
    nav.classList.toggle("is-solid", window.scrollY > 24);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  if (toggle && nav) {
    toggle.addEventListener("click", () => nav.classList.toggle("is-open"));
  }

  const more = document.querySelector("[data-nav-more]");
  const moreBtn = document.querySelector("[data-nav-more-btn]");
  if (more && moreBtn) {
    moreBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = more.classList.toggle("is-open");
      moreBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", (e) => {
      if (!more.contains(e.target)) {
        more.classList.remove("is-open");
        moreBtn.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        more.classList.remove("is-open");
        moreBtn.setAttribute("aria-expanded", "false");
      }
    });
  }

  const reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
    );
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("is-in"));
  }

  const ring = document.querySelector("[data-ring]");
  const hero = document.querySelector("[data-hero]");
  if (ring && hero) {
    hero.addEventListener("pointermove", (e) => {
      const rect = hero.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width - 0.5) * 28;
      const y = ((e.clientY - rect.top) / rect.height - 0.5) * 18;
      ring.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
    });
  }

  const hint = document.querySelector("[data-run-hint]");
  if (hint) {
    hint.addEventListener("click", (e) => {
      e.preventDefault();
      alert(
        "Запуск GT/OS:\n\n1. Откройте папку D:\\GTOS\n2. Выполните: python run.py\n\nНужны файлы out\\vmlinuz и out\\gtos-rootfs.cpio.gz"
      );
    });
  }

  const disc = document.querySelector(".disc-ring-a");
  const stage = document.querySelector(".get-stage");
  if (disc && stage) {
    stage.addEventListener("pointermove", (e) => {
      const rect = stage.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      disc.style.transform = `rotateX(${(-y * 8).toFixed(2)}deg) rotateY(${(x * 10).toFixed(2)}deg)`;
    });
  }

  const supportForm = document.getElementById("supportForm");
  if (supportForm) {
    supportForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const name = (document.getElementById("supName") || {}).value || "";
      const topic = (document.getElementById("supTopic") || {}).value || "GT/OS";
      const body = (document.getElementById("supBody") || {}).value || "";
      const subject = encodeURIComponent(`[GT/OS] ${topic}`);
      const text = encodeURIComponent(
        `Имя: ${name}\nТема: ${topic}\n\n${body}\n\n— отправлено с сайта GT/OS`
      );
      window.location.href = `mailto:mikhail.lososka@gmail.com?subject=${subject}&body=${text}`;
    });
  }

  const edition = document.querySelector("[data-release-select]");
  const dlBtn = document.getElementById("dlBtn");
  const fileHint = document.querySelector("[data-filehint]");
  const relSummary = document.querySelector("[data-rel-summary]");
  if (edition && dlBtn) {
    const apply = () => {
      const opt = edition.options[edition.selectedIndex];
      if (!opt) return;
      const ready = opt.getAttribute("data-ready") === "1";
      const url = opt.getAttribute("data-url") || "";
      const name = opt.getAttribute("data-name") || "";
      const size = opt.getAttribute("data-size") || "";
      const bytes = opt.getAttribute("data-bytes") || "";
      const summary = opt.getAttribute("data-summary") || "";
      if (relSummary) relSummary.textContent = summary;
      if (ready && url) {
        dlBtn.setAttribute("href", url);
        dlBtn.removeAttribute("aria-disabled");
        dlBtn.classList.remove("is-disabled");
        if (fileHint)
          fileHint.innerHTML = bytes
            ? `<code>${name}</code> · ${size} <span class="ms-dl-bytes">(${bytes})</span>`
            : `<code>${name}</code> · ${size}`;
      } else {
        dlBtn.setAttribute("href", "#");
        dlBtn.setAttribute("aria-disabled", "true");
        dlBtn.classList.add("is-disabled");
        if (fileHint)
          fileHint.innerHTML =
            "ISO пока недоступен. Выполните <code>python make_iso.py --version " +
            opt.value +
            "</code>.";
      }
    };
    edition.addEventListener("change", apply);
    apply();
  }
})();
