import Foundation
import SwiftData
import SwiftUI

@Model
final class BudgetCategory {
    var id: UUID
    var name: String
    var symbol: String
    var colorHex: String
    var sortOrder: Int
    @Relationship(deleteRule: .nullify, inverse: \Transaction.category)
    var transactions: [Transaction] = []
    @Relationship(deleteRule: .cascade, inverse: \CategoryBudget.category)
    var budgets: [CategoryBudget] = []

    var color: Color {
        Color(hex: colorHex) ?? AppTheme.pineSoft
    }

    init(name: String, symbol: String, colorHex: String, sortOrder: Int = 0) {
        self.id = UUID()
        self.name = name
        self.symbol = symbol
        self.colorHex = colorHex
        self.sortOrder = sortOrder
    }
}

@Model
final class CategoryBudget {
    var id: UUID
    var monthlyLimit: Double
    var monthStart: Date
    var category: BudgetCategory?

    init(monthlyLimit: Double, monthStart: Date = Date().startOfMonth, category: BudgetCategory? = nil) {
        self.id = UUID()
        self.monthlyLimit = monthlyLimit
        self.monthStart = monthStart.startOfMonth
        self.category = category
    }
}

extension Color {
    init?(hex: String) {
        var cleaned = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.hasPrefix("#") { cleaned.removeFirst() }
        guard cleaned.count == 6, let value = UInt64(cleaned, radix: 16) else { return nil }
        let r = Double((value >> 16) & 0xFF) / 255
        let g = Double((value >> 8) & 0xFF) / 255
        let b = Double(value & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}

extension Date {
    var startOfMonth: Date {
        Calendar.current.date(from: Calendar.current.dateComponents([.year, .month], from: self)) ?? self
    }

    var endOfMonth: Date {
        guard let next = Calendar.current.date(byAdding: .month, value: 1, to: startOfMonth) else { return self }
        return Calendar.current.date(byAdding: .second, value: -1, to: next) ?? self
    }

    func isSameMonth(as other: Date) -> Bool {
        Calendar.current.isDate(self, equalTo: other, toGranularity: .month)
    }
}
