import { Link } from "react-router-dom";
import { EmptyState } from "@/components/States";

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      hint="The requested view does not exist."
      action={
        <Link to="/" className="text-accent hover:underline">
          Back to overview →
        </Link>
      }
    />
  );
}
