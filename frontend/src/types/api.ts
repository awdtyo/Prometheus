export type ConnectionStatus = "loading" | "online" | "offline";

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}
