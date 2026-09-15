// 生产构建挂在 /doc/ 子路径（vite base），开发环境 BASE_URL 为 "/"，路径原样
export const apiBase = (p) => import.meta.env.BASE_URL.replace(/\/$/, "") + p;

export async function api(path, opts = {}) {
  const res = await fetch(apiBase(path), {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || JSON.stringify(d)).join("；")
      : (typeof detail === "string" ? detail : detail?.msg) || "请求失败";
    throw new Error(msg);
  }
  return data;
}

export async function apiFormData(path, formData) {
  const res = await fetch(apiBase(path), { method: "POST", body: formData });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || JSON.stringify(d)).join("；")
      : (typeof detail === "string" ? detail : detail?.msg) || "请求失败";
    throw new Error(msg);
  }
  return data;
}

export async function apiDownload(path, payload) {
  const res = await fetch(apiBase(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("导出失败");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const cd = res.headers.get("content-disposition") || "";
  const m = cd.match(/filename=([^;]+)/);
  const filename = m ? decodeURIComponent(m[1].replace(/"/g, "")) : "export.xlsx";
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
