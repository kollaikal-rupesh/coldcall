import Foundation
import SwiftData

struct MonthSummary {
    var income: Double
    var expenses: Double
    var balance: Double { income - expenses }
    var net: Double { balance }
}

enum BudgetMath {
    static func summary(for transactions: [Transaction], in month: Date = .now) -> MonthSummary {
        let monthTransactions = transactions.filter { $0.date.isSameMonth(as: month) }
        let income = monthTransactions.filter { $0.kind == .income }.reduce(0) { $0 + $1.amount }
        let expenses = monthTransactions.filter { $0.kind == .expense }.reduce(0) { $0 + $1.amount }
        return MonthSummary(income: income, expenses: expenses)
    }

    static func spent(in category: BudgetCategory, month: Date = .now) -> Double {
        category.transactions
            .filter { $0.kind == .expense && $0.date.isSameMonth(as: month) }
            .reduce(0) { $0 + $1.amount }
    }

    static func budget(for category: BudgetCategory, month: Date = .now) -> CategoryBudget? {
        category.budgets.first { $0.monthStart.isSameMonth(as: month) }
            ?? category.budgets.sorted { $0.monthStart > $1.monthStart }.first
    }

    static func groupedByDay(_ transactions: [Transaction]) -> [(Date, [Transaction])] {
        let calendar = Calendar.current
        let grouped = Dictionary(grouping: transactions) { transaction in
            calendar.startOfDay(for: transaction.date)
        }
        return grouped.keys.sorted(by: >).compactMap { day in
            guard let items = grouped[day] else { return nil }
            return (day, items.sorted { $0.date > $1.date })
        }
    }

    static func categoryBreakdown(transactions: [Transaction], month: Date = .now) -> [(BudgetCategory, Double)] {
        let expenses = transactions.filter { $0.kind == .expense && $0.date.isSameMonth(as: month) }
        var totals: [PersistentIdentifier: (BudgetCategory, Double)] = [:]
        for expense in expenses {
            guard let category = expense.category else { continue }
            let current = totals[category.persistentModelID]?.1 ?? 0
            totals[category.persistentModelID] = (category, current + expense.amount)
        }
        return totals.values.sorted { $0.1 > $1.1 }
    }
}
