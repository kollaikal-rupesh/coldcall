import SwiftUI

struct TransactionRow: View {
    let transaction: Transaction

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill((transaction.category?.color ?? AppTheme.pineSoft).opacity(0.16))
                    .frame(width: 44, height: 44)
                Image(systemName: transaction.category?.symbol ?? (transaction.kind == .income ? "arrow.down.left" : "arrow.up.right"))
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(transaction.category?.color ?? AppTheme.pine)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text(transaction.title)
                    .font(.system(.body, design: .rounded, weight: .semibold))
                    .foregroundStyle(AppTheme.ink)
                    .lineLimit(1)
                Text(transaction.category?.name ?? transaction.kind.title)
                    .font(.system(.caption, design: .rounded))
                    .foregroundStyle(AppTheme.inkMuted)
            }

            Spacer(minLength: 8)

            VStack(alignment: .trailing, spacing: 3) {
                Text(Formatters.signedMoney(transaction.signedAmount))
                    .font(.system(.body, design: .rounded, weight: .bold))
                    .foregroundStyle(transaction.kind == .income ? AppTheme.income : AppTheme.ink)
                Text(Formatters.weekday.string(from: transaction.date))
                    .font(.system(.caption2, design: .rounded))
                    .foregroundStyle(AppTheme.inkMuted)
            }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .combine)
    }
}
