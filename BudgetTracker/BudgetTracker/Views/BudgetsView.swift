import SwiftUI
import SwiftData

struct BudgetsView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \BudgetCategory.sortOrder) private var categories: [BudgetCategory]
    @State private var editingCategory: BudgetCategory?
    @State private var draftLimit: String = ""

    private var budgetCategories: [BudgetCategory] {
        categories.filter { $0.name != "Salary" }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                ScreenBackground()

                ScrollView(showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 18) {
                        Text("Monthly caps keep spending intentional.")
                            .font(.system(.body, design: .rounded))
                            .foregroundStyle(AppTheme.inkMuted)
                            .padding(.top, 4)

                        ForEach(budgetCategories) { category in
                            let spent = BudgetMath.spent(in: category)
                            let limit = BudgetMath.budget(for: category)?.monthlyLimit ?? 0
                            Button {
                                editingCategory = category
                                draftLimit = limit > 0 ? String(format: "%.0f", limit) : ""
                            } label: {
                                BudgetProgressRow(category: category, spent: spent, limit: limit)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.bottom, 32)
                }
            }
            .navigationTitle("Budgets")
            .sheet(item: $editingCategory) { category in
                NavigationStack {
                    Form {
                        Section("Category") {
                            Label(category.name, systemImage: category.symbol)
                        }
                        Section("Monthly limit") {
                            TextField("Amount", text: $draftLimit)
                                .keyboardType(.decimalPad)
                                .font(.system(.body, design: .rounded))
                        }
                    }
                    .navigationTitle("Edit budget")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Cancel") { editingCategory = nil }
                        }
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Save") {
                                saveBudget(for: category)
                            }
                            .fontWeight(.semibold)
                        }
                    }
                }
                .presentationDetents([.medium])
            }
        }
    }

    private func saveBudget(for category: BudgetCategory) {
        let value = Double(draftLimit.replacingOccurrences(of: ",", with: "")) ?? 0
        if let existing = BudgetMath.budget(for: category) {
            existing.monthlyLimit = abs(value)
            existing.monthStart = Date().startOfMonth
        } else {
            let budget = CategoryBudget(monthlyLimit: abs(value), category: category)
            modelContext.insert(budget)
        }
        try? modelContext.save()
        editingCategory = nil
    }
}
