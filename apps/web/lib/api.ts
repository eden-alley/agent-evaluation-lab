import type {
  Project,
  AgentRegistration,
  AvailabilityReport,
  Health,
} from "./types";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
  ) {
    super(message);
  }
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const isComparison = /^\/comparisons(?:[/?#]|$)/.test(path);
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      signal: AbortSignal.timeout(isComparison ? 90000 : 12000),
      cache: "no-store",
    });
  } catch (error) {
    if (isComparison && error instanceof Error && error.name === "TimeoutError") {
      throw new ApiError(
        "等待超时，后端可能仍在处理。请先刷新清单，避免重复创建。",
        0,
        "API_TIMEOUT",
      );
    }
    throw new ApiError(
      "无法连接本地 API，请启动后端服务后重试。",
      0,
      "API_UNAVAILABLE",
    );
  }
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      body?.error?.message || "请求未完成，请稍后重试。",
      response.status,
      body?.error?.code || "REQUEST_FAILED",
    );
  return body as T;
}
export const api = {
  health: () => request<Health>("/health"),
  projects: () => request<{ items: Project[] }>("/projects"),
  createProject: (data: { name: string; description: string }) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateProject: (id: string, data: { name?: string; description?: string }) =>
    request<Project>(`/projects/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  agent: (projectId: string) =>
    request<AgentRegistration>(
      `/projects/${encodeURIComponent(projectId)}/agent`,
    ),
  saveAgent: (
    projectId: string,
    data: {
      name: string;
      source_path: string;
      python_executable: string;
      entrypoint: string;
      config?: Record<string, unknown>;
    },
  ) =>
    request<AgentRegistration>(
      `/projects/${encodeURIComponent(projectId)}/agent`,
      { method: "PUT", body: JSON.stringify(data) },
    ),
  checkAgent: (projectId: string) =>
    request<AvailabilityReport>(
      `/projects/${encodeURIComponent(projectId)}/agent/check`,
      { method: "POST" },
    ),
};
