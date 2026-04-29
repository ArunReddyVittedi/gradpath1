import { useState } from 'react';
import type { CompletedCourse, PlannedSemester, DashboardData } from '../types';
import { DashboardCard } from './DashboardCard';

type DashboardPanelProps = {
  dashboard: DashboardData;
  loading: boolean;
  sessionId: string;
  lastAnalysisTimestamp: string | null;
};

// ── Semester sort order ───────────────────────────────────────────
const TERM_ORDER: Record<string, number> = { Spring: 0, Summer: 1, Fall: 2 };

function parseTerm(term: string): { label: string; year: number; order: number } {
  const parts = term.trim().split(/\s+/);
  const year = parseInt(parts[parts.length - 1]) || 9999;
  const season = parts[0] || '';
  return { label: term, year, order: TERM_ORDER[season] ?? 1 };
}

function sortTerms(terms: string[]): string[] {
  return [...terms].sort((a, b) => {
    const ta = parseTerm(a);
    const tb = parseTerm(b);
    if (ta.year !== tb.year) return ta.year - tb.year;
    return ta.order - tb.order;
  });
}

function groupBySemester(courses: CompletedCourse[]): Record<string, CompletedCourse[]> {
  return courses.reduce((acc, course) => {
    const term = course.term || 'Unknown Term';
    if (!acc[term]) acc[term] = [];
    acc[term].push(course);
    return acc;
  }, {} as Record<string, CompletedCourse[]>);
}

// ── Accordion component ───────────────────────────────────────────
function SemesterAccordion({ courses }: { courses: CompletedCourse[] }) {
  const grouped = groupBySemester(courses);
  const terms = sortTerms(Object.keys(grouped));
  const [open, setOpen] = useState<Set<string>>(new Set());

  const toggle = (term: string) => {
    setOpen(prev => {
      const next = new Set(prev);
      next.has(term) ? next.delete(term) : next.add(term);
      return next;
    });
  };

  return (
    <div className="semester-accordion">
      {terms.map(term => {
        const termCourses = grouped[term];
        const totalCredits = termCourses.reduce((s, c) => s + (c.credits || 0), 0);
        const isOpen = open.has(term);
        return (
          <div key={term} className="semester-block">
            <button className="semester-header" onClick={() => toggle(term)}>
              <span className="semester-chevron">{isOpen ? '▾' : '▸'}</span>
              <span className="semester-name">{term}</span>
              <span className="semester-meta">
                {termCourses.length} course{termCourses.length !== 1 ? 's' : ''} · {totalCredits} cr
              </span>
            </button>
            {isOpen && (
              <ul className="semester-course-list">
                {termCourses.map(course => (
                  <li key={course.course_id} className="semester-course-item">
                    <div className="semester-course-main">
                      <strong>{course.course_id}</strong>
                      <span>{course.title}</span>
                    </div>
                    <div className="semester-course-meta">
                      {course.grade && <span className="pill">{course.grade}</span>}
                      <span className="pill">{course.credits} cr</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PlannedSemesterAccordion({ semesters }: { semesters: PlannedSemester[] }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (term: string) => {
    setOpen(prev => {
      const next = new Set(prev);
      next.has(term) ? next.delete(term) : next.add(term);
      return next;
    });
  };

  return (
    <div className="semester-accordion planned-accordion">
      <div className="planned-accordion__label">Planned semesters</div>
      {semesters.map(sem => {
        const isOpen = open.has(sem.term);
        return (
          <div key={sem.term} className="semester-block semester-block--planned">
            <button className="semester-header" onClick={() => toggle(sem.term)}>
              <span className="semester-chevron">{isOpen ? '▾' : '▸'}</span>
              <span className="semester-name">{sem.term}</span>
              <span className="semester-meta">
                {sem.courses.length} course{sem.courses.length !== 1 ? 's' : ''} · {sem.total_credits} cr
              </span>
              <span className="pill planned-pill">Planned</span>
            </button>
            {isOpen && (
              <ul className="semester-course-list">
                {sem.courses.map((course: import('../types').PlannedCourse) => (
                  <li key={course.course_id} className="semester-course-item">
                    <div className="semester-course-main">
                      <strong>{course.course_id}</strong>
                      <span>{course.title}</span>
                    </div>
                    <div className="semester-course-meta">
                      <span className="pill">{course.credits} cr</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>;
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return 'Not analyzed yet';
  }

  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? 'Not analyzed yet'
    : date.toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      });
}

export function DashboardPanel({
  dashboard,
  loading,
  sessionId,
  lastAnalysisTimestamp,
}: DashboardPanelProps) {
  const { student, progress_summary, completed_courses, recommended_courses, advising_notes, planned_semesters } = dashboard;

  return (
    <div className="dashboard-panel">
      <div className="session-strip" aria-live="polite">
        <div className="session-chip">
          <span>Session</span>
          <strong>{sessionId ? sessionId.slice(0, 8) : 'pending'}</strong>
        </div>
        <div className="session-chip">
          <span>Last analysis</span>
          <strong>{loading ? 'Analyzing now...' : formatTimestamp(lastAnalysisTimestamp)}</strong>
        </div>
      </div>

      <header className="hero-card">
        <div className="hero-card__content">
          <span className="hero-card__badge">GradPath</span>
          <h1>AI-powered academic planning assistant</h1>
          <p>
            AI-powered academic planning assistant that analyzes student history and suggests
            next-semester courses, degree progress, and graduation path guidance.
          </p>
        </div>
        <div className="hero-card__meta">
          <div>
            <span>Student</span>
            <strong>{student.student_name}</strong>
          </div>
          <div>
            <span>Target term</span>
            <strong>{progress_summary.target_semester}</strong>
          </div>
          <div>
            <span>Progress</span>
            <strong>{progress_summary.percent_complete}% complete</strong>
          </div>
        </div>
      </header>

      <div className="dashboard-grid">
        <DashboardCard title="Student Academic History" eyebrow="Read only">
          <div className="student-meta">
            <div>
              <span>Student ID</span>
              <strong>{student.student_id}</strong>
            </div>
            <div>
              <span>Major</span>
              <strong>{student.major}</strong>
            </div>
            <div>
              <span>Current semester</span>
              <strong>{student.current_semester}</strong>
            </div>
            {student.student_type && (
              <div>
                <span>Student type</span>
                <strong style={{ textTransform: 'capitalize' }}>{student.student_type}</strong>
              </div>
            )}
            {student.gpa != null && (
              <div>
                <span>GPA</span>
                <strong>{student.gpa.toFixed(2)}</strong>
              </div>
            )}
            {student.career_goal && (
              <div>
                <span>Career goal</span>
                <strong>{student.career_goal}</strong>
              </div>
            )}
            {student.expected_graduation && (
              <div>
                <span>Expected graduation</span>
                <strong>{student.expected_graduation}</strong>
              </div>
            )}
          </div>
          {completed_courses.length ? (
            <SemesterAccordion courses={completed_courses} />
          ) : (
            <EmptyState text="No transcript uploaded yet." />
          )}
          {planned_semesters.length > 0 && (
            <PlannedSemesterAccordion semesters={planned_semesters} />
          )}
        </DashboardCard>

        <DashboardCard title="Degree Progress Summary" eyebrow="Auto-updated">
          <div className="stats-row">
            <div className="stat">
              <span>Credits earned</span>
              <strong>{progress_summary.credits_earned}</strong>
            </div>
            <div className="stat">
              <span>Required courses done</span>
              <strong>
                {progress_summary.required_courses_completed}/{progress_summary.required_courses_total}
              </strong>
            </div>
            <div className="stat">
              <span>Credits to graduate</span>
              <strong>{progress_summary.credits_to_graduate}</strong>
            </div>
          </div>
          <div className="progress-meter">
            <div
              className="progress-meter__fill"
              style={{ width: `${Math.max(progress_summary.percent_complete, 4)}%` }}
            />
          </div>
          <p className="support-text">
            GradPath keeps this panel read-only so only agent analysis can update degree progress.
          </p>
        </DashboardCard>

        <DashboardCard title="Suggested Next Courses" eyebrow="Agent recommendations">
          {recommended_courses.length ? (
            <ul className="recommendation-list">
              {recommended_courses.map((course) => (
                <li key={course.course_id} className="recommendation-list__item">
                  <div>
                    <strong>{course.course_id}</strong>
                    <span>{course.title}</span>
                  </div>
                  <div>
                    <span className="pill">{course.credits} credits</span>
                  </div>
                  <p>{course.reason}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="Recommendations will appear here after analysis." />
          )}
        </DashboardCard>

        <DashboardCard title="Notes / Advising Insights / Warnings" eyebrow="Agent insights">
          {loading ? (
            <div className="skeleton-list">
              <div className="skeleton-line" />
              <div className="skeleton-line" />
              <div className="skeleton-line short" />
            </div>
          ) : advising_notes.length ? (
            <ul className="notes-list">
              {advising_notes.map((note, index) => (
                <li key={`${note.title}-${index}`} className={`note note--${note.level}`}>
                  <strong>{note.title}</strong>
                  <p>{note.message}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="Advising notes will appear here after GradPath completes analysis." />
          )}
        </DashboardCard>
      </div>
    </div>
  );
}
