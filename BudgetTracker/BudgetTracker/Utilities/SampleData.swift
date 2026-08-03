import Foundation
import SwiftData

enum SampleData {
    static func seedIfNeeded(context: ModelContext) {
        var descriptor = FetchDescriptor<BudgetCategory>()
        descriptor.fetchLimit = 1
        let existing = (try? context.fetch(descriptor)) ?? []
        guard existing.isEmpty else { return }

        let categories: [(String, String, String, Double)] = [
            ("Groceries", "cart.fill", "2F8F6B", 450),
            ("Dining", "fork.knife", "D65A4C", 220),
            ("Transport", "car.fill", "4D85A0", 160),
            ("Home", "house.fill", "C79A38", 900),
            ("Fun", "ticket.fill", "6B8F71", 120),
            ("Health", "heart.fill", "B85C68", 100),
            ("Salary", "banknote.fill", "2F6B5A", 0)
        ]

        var created: [BudgetCategory] = []
        for (index, item) in categories.enumerated() {
            let category = BudgetCategory(
                name: item.0,
                symbol: item.1,
                colorHex: item.2,
                sortOrder: index
            )
            context.insert(category)
            created.append(category)

            if item.3 > 0 {
                let budget = CategoryBudget(monthlyLimit: item.3, category: category)
                context.insert(budget)
            }
        }

        let calendar = Calendar.current
        let today = Date()

        let samples: [(String, Double, TransactionKind, String, Int)] = [
            ("Paycheck", 4200, .income, "Salary", 0),
            ("Weekly groceries", 86.42, .expense, "Groceries", -1),
            ("Coffee & lunch", 24.50, .expense, "Dining", -1),
            ("Metro pass", 72.00, .expense, "Transport", -3),
            ("Rent", 1800, .expense, "Home", -2),
            ("Farmers market", 38.20, .expense, "Groceries", -4),
            ("Movie night", 32.00, .expense, "Fun", -5),
            ("Pharmacy", 18.75, .expense, "Health", -6),
            ("Dinner out", 64.10, .expense, "Dining", -7),
            ("Gas", 48.00, .expense, "Transport", -8),
            ("Side gig", 250, .income, "Salary", -10)
        ]

        for sample in samples {
            let category = created.first { $0.name == sample.3 }
            let date = calendar.date(byAdding: .day, value: sample.4, to: today) ?? today
            let transaction = Transaction(
                title: sample.0,
                amount: sample.1,
                kind: sample.2,
                date: date,
                category: category
            )
            context.insert(transaction)
        }

        try? context.save()
    }
}
