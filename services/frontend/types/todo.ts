export interface Todo {
  id: string;
  title: string;
  description?: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'pending' | 'completed';
  due_date?: string;
  category?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export type TodoPriority = 'low' | 'medium' | 'high' | 'urgent';
export type TodoStatus = 'pending' | 'completed';

export interface TodoFilter {
  status?: 'all' | 'pending' | 'completed';
  priority?: 'all' | 'low' | 'medium' | 'high' | 'urgent';
  category?: string;
}
