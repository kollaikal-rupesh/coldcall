import SwiftUI
import SwiftData

struct AddTransactionView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \BudgetCategory.sortOrder) private var categories: [BudgetCategory]

    @State private var title = ""
    @State private var amount = ""
    @State private var kind: TransactionKind = .expense
    @State private var date = Date()
    @State private var note = ""
    @State private var selectedCategory: BudgetCategory?
    @State private var showError = false
    @FocusState private var amountFocused: Bool

    private var availableCategories: [BudgetCategory] {
        if kind == .income {
            return categories.filter { $0.name == "Salary" } + categories.filter { $0.name != "Salary" }
        }
        return categories.filter { $0.name != "Salary" }
    }

    private var canSave: Bool {
        !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (Double(amount.replacingOccurrences(of: ",", with: "")) ?? 0) > 0
    }

    var body: some View {
        NavigationStack {
            ZStack {
                ScreenBackground()

                Form {
                    Section {
                        Picker("Type", selection: $kind) {
                            ForEach(TransactionKind.allCases) { item in
                                Text(item.title).tag(item)
                            }
                        }
                        .pickerStyle(.segmented)
                        .listRowBackground(Color.clear)
                    }

                    Section("Details") {
                        TextField("Title", text: $title)
                            .font(.system(.body, design: .rounded))
                        TextField("Amount", text: $amount)
                            .keyboardType(.decimalPad)
                            .font(.system(.title2, design: .rounded, weight: .bold))
                            .focused($amountFocused)
                        DatePicker("Date", selection: $date, displayedComponents: .date)
                    }

                    Section("Category") {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 10) {
                                ForEach(availableCategories) { category in
                                    CategoryChip(
                                        category: category,
                                        selected: selectedCategory?.id == category.id
                                    ) {
                                        selectedCategory = category
                                    }
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }

                    Section("Note") {
                        TextField("Optional note", text: $note, axis: .vertical)
                            .lineLimit(3...5)
                    }
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("New entry")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .fontWeight(.bold)
                        .disabled(!canSave)
                }
            }
            .onAppear {
                amountFocused = true
                if selectedCategory == nil {
                    selectedCategory = availableCategories.first
                }
            }
            .onChange(of: kind) { _, _ in
                if let selectedCategory, !availableCategories.contains(where: { $0.id == selectedCategory.id }) {
                    self.selectedCategory = availableCategories.first
                }
            }
            .alert("Check the amount", isPresented: $showError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text("Enter a title and an amount greater than zero.")
            }
        }
    }

    private func save() {
        guard canSave,
              let value = Double(amount.replacingOccurrences(of: ",", with: "")),
              value > 0 else {
            showError = true
            return
        }

        let transaction = Transaction(
            title: title.trimmingCharacters(in: .whitespacesAndNewlines),
            amount: value,
            kind: kind,
            date: date,
            note: note.trimmingCharacters(in: .whitespacesAndNewlines),
            category: selectedCategory
        )
        modelContext.insert(transaction)
        try? modelContext.save()
        dismiss()
    }
}

private struct CategoryChip: View {
    let category: BudgetCategory
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: category.symbol)
                Text(category.name)
                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(selected ? category.color : category.color.opacity(0.12))
            .foregroundStyle(selected ? Color.white : AppTheme.ink)
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}
