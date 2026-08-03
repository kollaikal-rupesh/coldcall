const CATEGORIES = [
  { id: 'groceries', name: 'Groceries', emoji: '🛒', color: '#2F8F6B', limit: 450 },
  { id: 'dining', name: 'Dining', emoji: '🍽️', color: '#D65A4C', limit: 220 },
  { id: 'transport', name: 'Transport', emoji: '🚗', color: '#4D85A0', limit: 160 },
  { id: 'home', name: 'Home', emoji: '🏠', color: '#C79A38', limit: 900 },
  { id: 'fun', name: 'Fun', emoji: '🎟️', color: '#6B8F71', limit: 120 },
  { id: 'health', name: 'Health', emoji: '❤️', color: '#B85C68', limit: 100 },
  { id: 'salary', name: 'Salary', emoji: '💵', color: '#2F6B5A', limit: 0 },
]

function daysAgo(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  d.setHours(12, 0, 0, 0)
  return d.toISOString()
}

const SAMPLE_TRANSACTIONS = [
  { id: 't1', title: 'Paycheck', amount: 4200, kind: 'income', categoryId: 'salary', date: daysAgo(0), note: '' },
  { id: 't2', title: 'Weekly groceries', amount: 86.42, kind: 'expense', categoryId: 'groceries', date: daysAgo(1), note: '' },
  { id: 't3', title: 'Coffee & lunch', amount: 24.5, kind: 'expense', categoryId: 'dining', date: daysAgo(1), note: '' },
  { id: 't4', title: 'Metro pass', amount: 72, kind: 'expense', categoryId: 'transport', date: daysAgo(3), note: '' },
  { id: 't5', title: 'Rent', amount: 1800, kind: 'expense', categoryId: 'home', date: daysAgo(2), note: '' },
  { id: 't6', title: 'Farmers market', amount: 38.2, kind: 'expense', categoryId: 'groceries', date: daysAgo(4), note: '' },
  { id: 't7', title: 'Movie night', amount: 32, kind: 'expense', categoryId: 'fun', date: daysAgo(5), note: '' },
  { id: 't8', title: 'Pharmacy', amount: 18.75, kind: 'expense', categoryId: 'health', date: daysAgo(6), note: '' },
  { id: 't9', title: 'Dinner out', amount: 64.1, kind: 'expense', categoryId: 'dining', date: daysAgo(7), note: '' },
  { id: 't10', title: 'Gas', amount: 48, kind: 'expense', categoryId: 'transport', date: daysAgo(8), note: '' },
  { id: 't11', title: 'Side gig', amount: 250, kind: 'income', categoryId: 'salary', date: daysAgo(10), note: '' },
]

const STORAGE_KEY = 'ledger-budget-tracker-v1'

export function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    /* ignore */
  }
  return {
    categories: CATEGORIES,
    transactions: SAMPLE_TRANSACTIONS,
  }
}

export function saveState(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

export function money(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value)
}

export function signedMoney(value) {
  const formatted = money(Math.abs(value))
  if (value > 0) return `+${formatted}`
  if (value < 0) return `-${formatted}`
  return formatted
}

export function monthLabel(date = new Date()) {
  return new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' }).format(date)
}

export function shortDate(iso) {
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(iso))
}

export function sameMonth(iso, date = new Date()) {
  const d = new Date(iso)
  return d.getFullYear() === date.getFullYear() && d.getMonth() === date.getMonth()
}

export function categoryById(categories, id) {
  return categories.find((c) => c.id === id)
}

export function monthSummary(transactions) {
  const monthTx = transactions.filter((t) => sameMonth(t.date))
  const income = monthTx.filter((t) => t.kind === 'income').reduce((s, t) => s + t.amount, 0)
  const expenses = monthTx.filter((t) => t.kind === 'expense').reduce((s, t) => s + t.amount, 0)
  return { income, expenses, balance: income - expenses }
}

export function categoryBreakdown(transactions, categories) {
  const totals = new Map()
  for (const t of transactions.filter((x) => x.kind === 'expense' && sameMonth(x.date))) {
    totals.set(t.categoryId, (totals.get(t.categoryId) || 0) + t.amount)
  }
  return [...totals.entries()]
    .map(([id, amount]) => ({ category: categoryById(categories, id), amount }))
    .filter((x) => x.category)
    .sort((a, b) => b.amount - a.amount)
}

export function spentInCategory(transactions, categoryId) {
  return transactions
    .filter((t) => t.kind === 'expense' && t.categoryId === categoryId && sameMonth(t.date))
    .reduce((s, t) => s + t.amount, 0)
}
