import { useEffect, useMemo, useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'
import {
  categoryBreakdown,
  categoryById,
  loadState,
  money,
  monthLabel,
  monthSummary,
  saveState,
  shortDate,
  signedMoney,
  spentInCategory,
} from './data.js'

const TABS = [
  { id: 'home', label: 'Home' },
  { id: 'activity', label: 'Activity' },
  { id: 'budgets', label: 'Budgets' },
]

function uid() {
  return crypto.randomUUID()
}

export default function App() {
  const [tab, setTab] = useState('home')
  const [state, setState] = useState(loadState)
  const [showAdd, setShowAdd] = useState(false)
  const [editingBudget, setEditingBudget] = useState(null)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  useEffect(() => {
    saveState(state)
  }, [state])

  const summary = useMemo(() => monthSummary(state.transactions), [state.transactions])
  const breakdown = useMemo(
    () => categoryBreakdown(state.transactions, state.categories),
    [state.transactions, state.categories],
  )
  const recent = useMemo(
    () => [...state.transactions].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 6),
    [state.transactions],
  )

  const filtered = useMemo(() => {
    return [...state.transactions]
      .sort((a, b) => new Date(b.date) - new Date(a.date))
      .filter((t) => {
        const kindOk = filter === 'all' || t.kind === filter
        const q = search.trim().toLowerCase()
        const cat = categoryById(state.categories, t.categoryId)
        const searchOk =
          !q ||
          t.title.toLowerCase().includes(q) ||
          (cat?.name || '').toLowerCase().includes(q)
        return kindOk && searchOk
      })
  }, [state.transactions, state.categories, filter, search])

  function addTransaction(entry) {
    setState((prev) => ({
      ...prev,
      transactions: [{ id: uid(), note: '', ...entry }, ...prev.transactions],
    }))
    setShowAdd(false)
    setTab('activity')
  }

  function deleteTransaction(id) {
    setState((prev) => ({
      ...prev,
      transactions: prev.transactions.filter((t) => t.id !== id),
    }))
  }

  function updateBudget(categoryId, limit) {
    setState((prev) => ({
      ...prev,
      categories: prev.categories.map((c) =>
        c.id === categoryId ? { ...c, limit: Math.max(0, limit) } : c,
      ),
    }))
    setEditingBudget(null)
  }

  return (
    <div className="app-shell">
      {tab === 'home' && (
        <HomeView
          summary={summary}
          breakdown={breakdown}
          recent={recent}
          categories={state.categories}
          onAdd={() => setShowAdd(true)}
        />
      )}
      {tab === 'activity' && (
        <ActivityView
          transactions={filtered}
          categories={state.categories}
          filter={filter}
          search={search}
          onFilter={setFilter}
          onSearch={setSearch}
          onDelete={deleteTransaction}
        />
      )}
      {tab === 'budgets' && (
        <BudgetsView
          categories={state.categories.filter((c) => c.id !== 'salary')}
          transactions={state.transactions}
          onEdit={setEditingBudget}
        />
      )}

      <button className="fab" aria-label="Add transaction" onClick={() => setShowAdd(true)}>
        +
      </button>

      <nav className="tabbar" aria-label="Main">
        {TABS.map((item) => (
          <button
            key={item.id}
            className={`tab ${tab === item.id ? 'active' : ''}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {showAdd && (
        <AddSheet
          categories={state.categories}
          onClose={() => setShowAdd(false)}
          onSave={addTransaction}
        />
      )}

      {editingBudget && (
        <BudgetSheet
          category={editingBudget}
          onClose={() => setEditingBudget(null)}
          onSave={updateBudget}
        />
      )}
    </div>
  )
}

function HomeView({ summary, breakdown, recent, categories, onAdd }) {
  return (
    <>
      <p className="muted" style={{ margin: 0, fontWeight: 600 }}>
        {monthLabel()}
      </p>
      <h1 className="brand">Ledger</h1>

      <section className="hero">
        <div className="label">Available this month</div>
        <div className="balance">{money(summary.balance)}</div>
        <div className="label">
          {summary.balance >= 0 ? "You're on track" : 'Spending ahead of income'}
        </div>
      </section>

      <div className="stats">
        <div className="stat">
          <div className="kicker" style={{ color: 'var(--pine-soft)' }}>
            In
          </div>
          <div className="value">{money(summary.income)}</div>
        </div>
        <div className="stat">
          <div className="kicker" style={{ color: 'var(--coral)' }}>
            Out
          </div>
          <div className="value">{money(summary.expenses)}</div>
        </div>
      </div>

      {breakdown.length > 0 && (
        <section className="panel" style={{ marginTop: 18 }}>
          <div className="section-title" style={{ marginTop: 0 }}>
            <h2>Where it went</h2>
          </div>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={breakdown.map((b) => ({
                    name: b.category.name,
                    value: b.amount,
                    color: b.category.color,
                  }))}
                  dataKey="value"
                  innerRadius={58}
                  outerRadius={82}
                  paddingAngle={2}
                >
                  {breakdown.map((b) => (
                    <Cell key={b.category.id} fill={b.category.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="legend">
            {breakdown.slice(0, 4).map((b) => (
              <div className="legend-row" key={b.category.id}>
                <span>
                  <span className="dot" style={{ background: b.category.color }} />
                  {b.category.name}
                </span>
                <strong className="muted">{money(b.amount)}</strong>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="section-title">
        <h2>Recent</h2>
        <button className="linkish" onClick={onAdd}>
          Add
        </button>
      </div>
      <section className="panel">
        <div className="tx-list">
          {recent.map((t) => (
            <TransactionRow key={t.id} tx={t} category={categoryById(categories, t.categoryId)} />
          ))}
        </div>
      </section>
    </>
  )
}

function ActivityView({ transactions, categories, filter, search, onFilter, onSearch, onDelete }) {
  return (
    <>
      <h1 className="brand" style={{ fontSize: '2rem' }}>
        Activity
      </h1>
      <input
        className="search"
        placeholder="Search transactions"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
      />
      <div className="filters">
        {[
          ['all', 'All'],
          ['income', 'Income'],
          ['expense', 'Expense'],
        ].map(([id, label]) => (
          <button
            key={id}
            className={`pill ${filter === id ? 'active' : ''}`}
            onClick={() => onFilter(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <section className="panel">
        {transactions.length === 0 ? (
          <div className="empty">No activity. Try another filter or add a transaction.</div>
        ) : (
          <div className="tx-list">
            {transactions.map((t) => (
              <div key={t.id}>
                <TransactionRow tx={t} category={categoryById(categories, t.categoryId)} />
                <button className="btn danger" onClick={() => onDelete(t.id)}>
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

function BudgetsView({ categories, transactions, onEdit }) {
  return (
    <>
      <h1 className="brand" style={{ fontSize: '2rem' }}>
        Budgets
      </h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Monthly caps keep spending intentional.
      </p>
      {categories.map((category) => {
        const spent = spentInCategory(transactions, category.id)
        const limit = category.limit || 0
        const hasLimit = limit > 0
        const over = hasLimit && spent > limit
        const progress = hasLimit ? Math.min(spent / limit, 1) : spent > 0 ? 0.08 : 0
        return (
          <button
            key={category.id}
            className="budget-card"
            onClick={() => onEdit(category)}
          >
            <div className="budget-top">
              <span>
                {category.emoji} {category.name}
              </span>
              <span className="muted">
                {hasLimit ? `${money(spent)} / ${money(limit)}` : `${money(spent)} spent`}
              </span>
            </div>
            <div className="bar">
              <span
                style={{
                  width: `${progress * 100}%`,
                  background: over ? 'var(--coral)' : category.color,
                }}
              />
            </div>
            <p className={`budget-status ${over ? 'over' : ''}`}>
              {!hasLimit && 'Tap to set a monthly limit'}
              {hasLimit && over && `Over by ${money(spent - limit)}`}
              {hasLimit && !over && `${money(limit - spent)} left this month`}
            </p>
          </button>
        )
      })}
    </>
  )
}

function TransactionRow({ tx, category }) {
  const signed = tx.kind === 'income' ? tx.amount : -tx.amount
  return (
    <div className="tx-row">
      <div className="avatar" style={{ background: `${category?.color || '#388c75'}22` }}>
        {category?.emoji || (tx.kind === 'income' ? '↓' : '↑')}
      </div>
      <div>
        <p className="tx-title">{tx.title}</p>
        <p className="tx-meta">{category?.name || tx.kind}</p>
      </div>
      <div>
        <div className={`tx-amount ${tx.kind === 'income' ? 'income' : ''}`}>
          {signedMoney(signed)}
        </div>
        <p className="tx-date">{shortDate(tx.date)}</p>
      </div>
    </div>
  )
}

function AddSheet({ categories, onClose, onSave }) {
  const [kind, setKind] = useState('expense')
  const [title, setTitle] = useState('')
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [note, setNote] = useState('')
  const available = kind === 'income' ? categories : categories.filter((c) => c.id !== 'salary')
  const [categoryId, setCategoryId] = useState(available[0]?.id)

  useEffect(() => {
    if (!available.some((c) => c.id === categoryId)) {
      setCategoryId(available[0]?.id)
    }
  }, [kind, available, categoryId])

  function submit(e) {
    e.preventDefault()
    const value = Number(String(amount).replace(',', ''))
    if (!title.trim() || !(value > 0)) return
    onSave({
      title: title.trim(),
      amount: value,
      kind,
      categoryId,
      date: new Date(`${date}T12:00:00`).toISOString(),
      note: note.trim(),
    })
  }

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <form className="sheet" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>New entry</h3>
        <div className="segment">
          <button type="button" className={kind === 'expense' ? 'active' : ''} onClick={() => setKind('expense')}>
            Expense
          </button>
          <button type="button" className={kind === 'income' ? 'active' : ''} onClick={() => setKind('income')}>
            Income
          </button>
        </div>
        <div className="field">
          <label htmlFor="title">Title</label>
          <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Coffee" required />
        </div>
        <div className="field">
          <label htmlFor="amount">Amount</label>
          <input
            id="amount"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="date">Date</label>
          <input id="date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <label className="muted" style={{ fontSize: '0.82rem', fontWeight: 700 }}>
          Category
        </label>
        <div className="category-row">
          {available.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`cat-chip ${categoryId === c.id ? 'active' : ''}`}
              style={categoryId === c.id ? { background: c.color } : { color: c.color }}
              onClick={() => setCategoryId(c.id)}
            >
              {c.emoji} {c.name}
            </button>
          ))}
        </div>
        <div className="field">
          <label htmlFor="note">Note</label>
          <textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="sheet-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn primary">
            Save
          </button>
        </div>
      </form>
    </div>
  )
}

function BudgetSheet({ category, onClose, onSave }) {
  const [limit, setLimit] = useState(category.limit ? String(category.limit) : '')

  function submit(e) {
    e.preventDefault()
    onSave(category.id, Number(String(limit).replace(',', '')) || 0)
  }

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <form className="sheet" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Edit budget</h3>
        <p style={{ marginTop: 0, fontWeight: 700 }}>
          {category.emoji} {category.name}
        </p>
        <div className="field">
          <label htmlFor="limit">Monthly limit</label>
          <input
            id="limit"
            inputMode="decimal"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            placeholder="0"
          />
        </div>
        <div className="sheet-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn primary">
            Save
          </button>
        </div>
      </form>
    </div>
  )
}
