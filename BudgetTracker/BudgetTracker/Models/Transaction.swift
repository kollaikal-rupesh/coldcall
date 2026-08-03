import Foundation
import SwiftData

enum TransactionKind: String, Codable, CaseIterable, Identifiable {
    case income
    case expense

    var id: String { rawValue }

    var title: String {
        switch self {
        case .income: return "Income"
        case .expense: return "Expense"
        }
    }
}

@Model
final class Transaction {
    var id: UUID
    var title: String
    var amount: Double
    var kindRaw: String
    var date: Date
    var note: String
    var category: BudgetCategory?

    var kind: TransactionKind {
        get { TransactionKind(rawValue: kindRaw) ?? .expense }
        set { kindRaw = newValue.rawValue }
    }

    var signedAmount: Double {
        kind == .income ? amount : -amount
    }

    init(
        title: String,
        amount: Double,
        kind: TransactionKind,
        date: Date = .now,
        note: String = "",
        category: BudgetCategory? = nil
    ) {
        self.id = UUID()
        self.title = title
        self.amount = abs(amount)
        self.kindRaw = kind.rawValue
        self.date = date
        self.note = note
        self.category = category
    }
}
