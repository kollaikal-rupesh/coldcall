import SwiftUI

struct BudgetProgressRow: View {
    let category: BudgetCategory
    let spent: Double
    let limit: Double

    private var hasLimit: Bool { limit > 0 }

    private var progress: Double {
        guard hasLimit else { return spent > 0 ? 0.08 : 0 }
        return min(spent / limit, 1.2)
    }

    private var remaining: Double { max(limit - spent, 0) }
    private var overBudget: Bool { hasLimit && spent > limit }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(category.name, systemImage: category.symbol)
                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
                    .foregroundStyle(AppTheme.ink)
                Spacer()
                Text(hasLimit
                     ? "\(Formatters.money(spent)) / \(Formatters.money(limit))"
                     : "\(Formatters.money(spent)) spent")
                    .font(.system(.caption, design: .rounded, weight: .medium))
                    .foregroundStyle(overBudget ? AppTheme.expense : AppTheme.inkMuted)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(AppTheme.ink.opacity(0.08))
                    Capsule()
                        .fill(overBudget ? AppTheme.expense : category.color)
                        .frame(width: max(spent > 0 ? 8 : 0, geo.size.width * min(progress, 1)))
                        .animation(.spring(response: 0.55, dampingFraction: 0.82), value: progress)
                }
            }
            .frame(height: 8)

            Text(statusText)
                .font(.system(.caption2, design: .rounded))
                .foregroundStyle(overBudget ? AppTheme.expense : AppTheme.inkMuted)
        }
        .padding(16)
        .background(AppTheme.surfaceElevated.opacity(0.88))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var statusText: String {
        if !hasLimit {
            return "Tap to set a monthly limit"
        }
        if overBudget {
            return "Over by \(Formatters.money(spent - limit))"
        }
        return "\(Formatters.money(remaining)) left this month"
    }
}
