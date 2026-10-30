/* =============================================================================
   Live Investigation Page
   -------------------------------------------------------
   Real-time investigation run monitoring via Server-Sent Events (SSE).
   Displays pipeline stage, progress percentage, stage-specific messages,
   and updates graph/timeline when relevant data becomes available.
   Handles reconnections, failed jobs, and completed investigation navigation.
   ============================================================================= */

import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/* -------------------------------------------------------
   Live investigation component
   ------------------------------------------------------- */

interface LiveInvestigationProps {
  /** Initial run ID (from POST /api/v1/runs) */
  initialRunId?: string;
}

/** SSE message types */
type SseMessageType = "progress" | "stage" | "message" | "complete" | "error" | "finished";

interface SseProgressMessage {
  type: "progress";
  progress: number; // 0-100
  stage?: string;
  message?: string;
}

interface SsStageMessage {
  type: "stage";
  stage: string;
  message?: string;
}

interface SsMessage {
  type: "message";
  message: string;
}

interface SsCompleteMessage {
  type: "complete";
  run_id: string;
  investigation_id: string;
  status: string;
  summary?: string;
}

interface SsErrorMessage {
  type: "error";
  error: string;
  code?: string;
}

interface SsFinishedMessage {
  type: "finished";
}

/** Union of all SSE message types */
type SseMessage =
  | SseProgressMessage
  | SsStageMessage
  | SsMessage
  | SsCompleteMessage
  | SsErrorMessage
  | SsFinishedMessage;

/** Backend progress state */
type ProgressState =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

interface LiveInvestigationState {
  runId: string | null;
  status: ProgressState;
  progress: number; // 0-100
  stage: string;
  message: string;
  /** SSE connection */
  eventSource?: EventSource;
  /** Latest graph data (nodes + edges) */
  graphData?: {
    nodes: any[];
    edges: any[];
  };
  /** Latest timeline events */
  timelineEvents?: any[];
  /** Whether the job has completed permanently */
  permanentlyCompleted: boolean;
}

/** Live Investigation page */
export function LiveInvestigationPage({ initialRunId }: LiveInvestigationProps = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [state, setState] = useState<LiveInvestigationState>({
    runId: initialRunId || null,
    status: "pending",
    progress: 0,
    stage: "initializing",
    message: "Initializing investigation run...",
    permanentlyCompleted: false,
  });

  // -------------------------------------------------------------------------
  // SSE connection and message handling
  // -------------------------------------------------------------------------

  useEffect(() => {
    const runId = state.runId;

    if (!runId) {
      // No run ID yet - wait for one or navigate to create run
      return;
    }

    // Create SSE connection to the run progress endpoint
    // In production, this would be: `/api/v1/runs/{runId}/sse`
    // For now, we simulate with a mock endpoint
    const source = new EventSource(`/api/v1/runs/${runId}/sse`);

    // Handle messages
    source.onmessage = (event) => {
      try {
        const data: SseMessage = JSON.parse(event.data);
        handleSseMessage(data);
      } catch (e) {
        console.error("Failed to parse SSE message:", e);
      }
    };

    // Handle connection errors
    source.onerror = (err) => {
      console.error("SSE error:", err);
      setState((prev) => ({
        ...prev,
        message: "Connection lost. Attempting reconnection..."
      }));

      // Attempt reconnection after delay
      setTimeout(() => {
        // Re-create the SSE connection
        const newSource = new EventSource(`/api/v1/runs/${runId}/sse`);
        newSource.onmessage = (event) => {
          try {
            const data: SseMessage = JSON.parse(event.data);
            handleSseMessage(data);
          } catch (e) {
            console.error("Failed to parse reconnection message:", e);
          }
        };
        // Keep reference alive
        state.eventSource?.close();
        // We need to update state - use a ref approach
        // For simplicity, just update status
        setState((prev) => ({
          ...prev,
          message: "Reconnected to progress stream.",
          status: prev.status,
        }));
      }, 3000);
    };

    // Cleanup on unmount
    return () => {
      source.close();
    };
  }, [state.runId]);

  // -------------------------------------------------------------------------
  // SSE message handler
  // -------------------------------------------------------------------------

  const handleSseMessage = (message: SseMessage) => {
    switch (message.type) {
      case "progress": {
        setState((prev) => ({
          ...prev,
          progress: message.progress,
          stage: message.stage || prev.stage,
          message: message.message || prev.message,
        }));
        break;
      }
      case "stage": {
        setState((prev) => ({
          ...prev,
          stage: message.stage,
          message: message.message || `Stage: ${message.stage}`,
        }));
        break;
      }
      case "message": {
        setState((prev) => ({
          ...prev,
          message: message.message,
        }));
        break;
      }
      case "complete": {
        // Navigate to investigation workspace
        setState({
          ...state,
          status: "completed",
          progress: 100,
          stage: "completed",
          message: "Investigation completed successfully.",
          permanentlyCompleted: true,
        });

        // Navigate after a brief delay
        const timeoutId = setTimeout(() => {
          navigate(`/workspace/${message.run_id}`);
        }, 2000);
        return clearTimeout(timeoutId);
      }
      case "error": {
        setState((prev) => ({
          ...prev,
          status: "failed",
          message: message.error || "Investigation failed.",
        }));

        // Handle failed jobs
        if (message.code === "ALREADY_COMPLETED") {
          // Navigate to the already completed investigation
          setTimeout(() => {
            navigate(`/workspace/${runId}`);
          }, 1500);
        }
        break;
      }
      case "finished": {
        setState((prev) => ({
          ...prev,
          status: "completed",
          progress: 100,
          stage: "finished",
          message: "Investigation finished.",
          permanentlyCompleted: true,
        }));
        break;
      }
      default:
        setState((prev) => ({
          ...prev,
          message: `Unknown message type: ${(message as any).type}`,
        }));
    }
  };

  // -------------------------------------------------------------------------
  // Initial run creation (if no run ID provided)
  // -------------------------------------------------------------------------

  useEffect(() => {
    // If no initial run ID, create a new investigation run
    if (!state.runId && !state.permanentlyCompleted) {
      const controller = new AbortController();

      fetch("/api/v1/runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          scenario_id: "scn_001", // Default scenario
          fault_config: {
            fault_type: "power_loss",
            target_subsystem: "power",
            start_time: new Date().toISOString(),
            duration_seconds: 120,
            magnitude: 0.25,
          },
        }),
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error("Failed to create run");
          }
          return response.json();
        })
        .then((data) => {
          setState({
            runId: data.run_id,
            status: "running",
            progress: 0,
            stage: "initializing",
            message: "Investigation run started.",
            permanentlyCompleted: false,
          });
        })
        .catch((err) => {
          setState((prev) => ({
            ...prev,
            message: `Failed to create investigation run: ${err.message}`,
            status: "failed",
          }));
        });

      return () => {
        controller.abort();
      };
    }
  }, [state.runId, state.permanentlyCompleted]);

  // -------------------------------------------------------------------------
  // Handle reconnection and already-completed jobs
  // -------------------------------------------------------------------------

  useEffect(() => {
    // If we have a permanently completed run, navigate away
    if (state.permanentlyCompleted && state.runId) {
      const timeoutId = setTimeout(() => {
        navigate(`/workspace/${state.runId}`);
      }, 3000);
      return clearTimeout(timeoutId);
    }
  }, [state.runId, state.permanentlyCompleted]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const { runId, status, progress, stage, message } = state;

  // Progress bar width
  const progressWidth = `${progress}%`;

  // Status badge styling
  const statusClass = {
    pending: "status--pending",
    running: "status--running",
    completed: "status--completed",
    failed: "status--failed",
    cancelled: "status--cancelled",
  }[status] || "status--pending";

  // Stage styling
  const stageClass = {
    initializing: "stage--initializing",
    running: "stage--running",
    completed: "stage--completed",
    failed: "stage--failed",
  }[stage] || "stage--initializing";

  // If run is completed permanently, show different content
  if (state.permanentlyCompleted && state.runId) {
    return (
      <section className="page live-investigation">
        <div className="page__header">
          <h2 className="page__title">Investigation Run</h2>
          <p className="page__subtitle">
            Run {state.runId} — Completed
          </p>
        </div>

        <div className="investigation-completed">
          <div className="completed-status">
            <span className={`status-dot status-dot--status--completed`} />
            <span className="status-text status-text--completed">
              Investigation completed successfully
            </span>
          </div>

          <div className="completed-details">
            <p><strong>Run ID:</strong> {state.runId}</p>
            <p><strong>Final status:</strong> Completed</p>
            <p><strong>Progress:</strong> 100%</p>
            <p><strong>Final stage:</strong> {stage}</p>
          </div>

          <button
            className="button button--primary"
            onClick={() => navigate(`/workspace/${state.runId}`)}
          >
            View Investigation Results
          </button>
        </div>
      </section>
    );
  }

  // If failed job
  if (status === "failed" && !permanentlyCompleted) {
    return (
      <section className="page live-investigation">
        <div className="page__header">
          <h2 className="page__title">Investigation Run</h2>
          <p className="page__subtitle">
            Run {runId || "—"} — Failed
          </p>
        </div>

        <div className="investigation-failed">
          <div className="failed-status">
            <span className="status-dot status-dot--status--failed" />
            <span className="status-text status-text--failed">
              Investigation failed
            </span>
          </div>

          <div className="failed-details">
            <p><strong>Run ID:</strong> {runId || "—"}</p>
            <p><strong>Error:</strong> {message}</p>
            <button
              className="button button--primary"
              onClick={() => navigate(`/workspace/${runId}`)}
            >
              View Investigation
            </button>
            <button
              className="button button--secondary"
              onClick={() => navigate("/")}
            >
              Return to Scenarios
            </button>
          </div>
        </div>
      </section>
    );
  }

  // Main live investigation display
  return (
    <section className="page live-investigation">
      <div className="live-investigation__header">
        <h2 className="page__title">Live Investigation</h2>
        <div className="live-investigation__controls">
          <span className={`status-badge status-badge--${statusClass}`}>
            {status}
          </span>
          <span className="progress-percentage">{progress}%</span>
        </div>
      </div>

      <div className="live-investigation__content">
        {/* Pipeline stage display */}
        <div className="pipeline-stage">
          <strong>Current Stage:</strong> {stage}
          {stage && stage !== "initializing" && <p className="stage-message">{message}</p>}
        </div>

        {/* Progress indicator */}
        <div className="progress-bar">
          <div
            className="progress-bar-fill"
            style={{ width: progressWidth }}
          /></div>
        </div>

        {/* Status message */}
        <p className="status-message">{message}</p>

        {/* SSE connection status */}
        {state.eventSource && state.eventSource.readyState === EventSource.CONNECTING && (
          <p className="sse-status">Connecting to progress stream...</p>
        )}
        {state.eventSource && state.eventSource.readyState === EventSource.OPEN && (
          <p className="sse-status">Connected to progress stream</p>
        )}
        {!state.eventSource && !state.permanentlyCompleted && (
          <p className="sse-status">Starting investigation run...</p>
        )}

        {/* Graph and timeline updates container */}
        <div className="data-updates">
          {progress > 0 && progress < 100 && (
            <p className="update-message">
              Graph and timeline will update when relevant data becomes available.
            </p>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="live-investigation__controls">
        {status === "running" && !state.permanentlyCompleted && (
          <button
            className="button button--secondary"
            onClick={() => navigate("/")}
          >
            Cancel Investigation
          </button>
        )}
        {status === "pending" && (
          <button
            className="button button--primary"
            onClick={() => {
              // Already handled by the useEffect above
            }}
          >
            Start Investigation
          </button>
        )}
      </div>
    </section>
  );
}