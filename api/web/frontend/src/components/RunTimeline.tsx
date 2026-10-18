import type { RunEvent } from "../types";

export default function RunTimeline({
  events,
  latestReview
}: {
  events: RunEvent[];
  latestReview?: { verdict?: string; round?: number };
}) {
  return (
    <section className="timeline" aria-label="Agent conversation">
      <div className="timeline-heading">
        <h2>Research group transcript</h2>
        {latestReview?.verdict && (
          <span className={`verdict ${latestReview.verdict}`}>
            round {latestReview.round ?? 1} · {latestReview.verdict}
          </span>
        )}
      </div>
      {events.length === 0 ? (
        <p className="empty">The transcript starts as soon as the brief is accepted.</p>
      ) : (
        <ol>
          {events.map((event) => (
            <li key={event.sequence}>
              <div className="event-head">
                <span className={`actor ${event.actor.toLowerCase().replace(/[^a-z]/g, "")}`}>{event.actor}</span>
                <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleTimeString()}</time>
              </div>
              <p>{event.message}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

