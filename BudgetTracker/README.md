# Ledger — iOS Budget Tracker

A native SwiftUI budget tracker for iPhone and iPad. Track income and expenses, set monthly category budgets, and see where your money goes — all stored on-device with SwiftData.

## Requirements

- macOS with Xcode 15.4+
- iOS 17.0+ deployment target

## Open & run

1. Open `BudgetTracker.xcodeproj` in Xcode
2. Select an iPhone simulator (or a connected device)
3. Set your Team under **Signing & Capabilities** if running on a device
4. Press **Run** (⌘R)

The app ships with sample transactions and budgets so the first launch feels populated. Data persists locally between launches.

## Features

- **Home** — month balance, income/out totals, spending breakdown chart, recent activity
- **Activity** — searchable transaction list with income/expense filters and swipe-to-delete
- **Budgets** — per-category monthly limits with progress and overspend warnings
- **Add entry** — income or expense with category, date, and optional note

## Project layout

```
BudgetTracker/
├── BudgetTrackerApp.swift          # App entry + SwiftData container
├── Models/                         # Transaction, categories, budgets
├── Views/                          # Tabs, forms, and shared rows
├── Theme/                          # Colors and background treatments
└── Utilities/                      # Formatting, summaries, sample seed data
```

## Web preview (no Xcode required)

A mobile browser preview lives in `web/`:

```bash
cd BudgetTracker/web
npm install
npm run dev
```

Same core flows as the iOS app (home, activity, budgets, add entry), with data stored in `localStorage`.

## Notes

- Bundle ID: `com.ledger.budgettracker`
- Display name: **Ledger**
- No backend or accounts — privacy-friendly local storage only
