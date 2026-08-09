export const REQUEST_STATUS = Object.freeze({
  IDLE: "idle",
  LOADING: "loading",
  SUCCESS: "success",
  EMPTY: "empty",
  ERROR: "error",
  DENIED: "denied",
});

export function createRequestState(status = REQUEST_STATUS.IDLE, data = null, error = null) {
  return Object.freeze({ status, data, error });
}
