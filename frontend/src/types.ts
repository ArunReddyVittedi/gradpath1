export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  attachment_name?: string | null;
};

export type CompletedCourse = {
  course_id: string;
  title: string;
  term?: string | null;
  grade?: string | null;
  credits: number;
};

export type ProgressSummary = {
  major: string;
  target_semester: string;
  credits_earned: number;
  required_courses_total: number;
  required_courses_completed: number;
  required_courses_remaining: number;
  percent_complete: number;
  total_recommended_credits: number;
};

export type RecommendedCourse = {
  course_id: string;
  title: string;
  credits: number;
  reason: string;
};

export type AdvisingNote = {
  level: 'info' | 'warning' | 'success';
  title: string;
  message: string;
};

export type StudentSnapshot = {
  student_name: string;
  student_id: string;
  major: string;
  current_semester: string;
  source: string;
};

export type DashboardData = {
  student: StudentSnapshot;
  completed_courses: CompletedCourse[];
  progress_summary: ProgressSummary;
  recommended_courses: RecommendedCourse[];
  advising_notes: AdvisingNote[];
};

export type SessionBootstrap = {
  session_id: string;
  dashboard: DashboardData;
  history: ChatMessage[];
};

export type ChatResponse = {
  session_id: string;
  reply: ChatMessage;
  dashboard: DashboardData;
  history: ChatMessage[];
};
