import { createBrowserRouter } from "react-router";
import { NotFoundPage } from "@/features/system/NotFoundPage";
import { SystemStatusPage } from "@/features/system/SystemStatusPage";

// Routes are added feature by feature (public site, auth, admin, workspace) in later phases.
export const router = createBrowserRouter([
  { path: "/", element: <SystemStatusPage /> },
  { path: "*", element: <NotFoundPage /> },
]);
