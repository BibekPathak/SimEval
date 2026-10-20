import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { OverviewPage } from "@/pages/OverviewPage";
import { TasksPage } from "@/pages/TasksPage";
import { NewEvaluationPage } from "@/pages/NewEvaluationPage";
import { ExperimentsPage } from "@/pages/ExperimentsPage";
import { ExperimentDetailPage } from "@/pages/ExperimentDetailPage";
import { ComparePage } from "@/pages/ComparePage";
import { EpisodePage } from "@/pages/EpisodePage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import "@/index.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "tasks", element: <TasksPage /> },
      { path: "new", element: <NewEvaluationPage /> },
      { path: "experiments", element: <ExperimentsPage /> },
      { path: "experiments/:id", element: <ExperimentDetailPage /> },
      { path: "compare", element: <ComparePage /> },
      { path: "episodes/:id", element: <EpisodePage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
