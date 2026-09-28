# frozen_string_literal: true

module RuboCop
  module Cop
    module Tenancy
      # Flags a query on a tenant-owned model's CONSTANT — `Invoice.find(params[:id])`,
      # `Invoice.where(...)`, `Invoice.includes(:lines).find(...)` — which reads across every tenant,
      # and points at the tenant-scoped association instead:
      # `Current.organization.invoices.find(params[:id])`.
      #
      #   Tenancy/ScopedLookup:
      #     Enabled: true
      #     SafeAutoCorrect: false          # `rubocop -a` reports it; only `-A` rewrites it
      #     Include: [app/controllers/**/*.rb]
      #     Exclude: [app/controllers/admin/**/*.rb]
      #     TenantScope: Current.organization
      #     TenantOwnedModels:
      #       Invoice: invoices
      #       Billing::CreditNote: credit_notes
      class ScopedLookup < Base
        extend AutoCorrector

        MSG = "`%<model>s.%<method>s` reads across every tenant. Scope it: `%<scoped>s.%<method>s`."

        # Every class method Active Record delegates to `all` — `ActiveRecord::Querying::QUERYING_METHODS`,
        # identical in Rails 8.0 and 8.1 — plus three outside it that also read the whole table. Fixed,
        # not configurable: RuboCop does not validate a local cop's keys, so a mistyped list would
        # silently check nothing. The spec asserts this still covers Rails' own list.
        RESTRICT_ON_SEND = (%i[
          find find_by find_by! take take! sole find_sole_by first first! last last! second
          second! third third! fourth fourth! fifth fifth! forty_two forty_two! third_to_last
          third_to_last! second_to_last second_to_last! exists? any? many? none? one?
          first_or_create first_or_create! first_or_initialize find_or_create_by
          find_or_create_by! find_or_initialize_by create_or_find_by create_or_find_by! destroy
          destroy_all delete delete_all update_all touch_all destroy_by delete_by find_each
          find_in_batches in_batches select reselect order regroup in_order_of reorder group limit
          offset joins left_joins left_outer_joins where rewhere invert_where preload
          extract_associated eager_load includes from lock readonly and or annotate
          optimizer_hints extending having create_with distinct references none unscope merge
          except only count average minimum maximum sum calculate pluck pick ids async_ids
          strict_loading excluding without with with_recursive async_count async_average
          async_minimum async_maximum async_sum async_pluck async_pick insert insert_all insert!
          insert_all! upsert upsert_all
        ] + %i[unscoped find_by_sql count_by_sql]).freeze

        def on_send(node)
          receiver = node.receiver
          return unless receiver&.const_type?

          model = receiver.const_name
          association = tenant_owned_models[model]
          return unless association

          target = association.empty? ? "<association>" : association
          scoped = [tenant_scope, target].compact.join(".")
          message = format(MSG, model: model, method: node.method_name, scoped: scoped)
          add_offense(node, message: message) do |corrector|
            corrector.replace(receiver, scoped) if tenant_scope && !association.empty?
          end
        end
        alias on_csend on_send

        private

        def tenant_owned_models
          cop_config.fetch("TenantOwnedModels", {}).to_h { |model, assoc| [model.to_s.delete_prefix("::"), assoc.to_s] }
        end

        def tenant_scope
          scope = cop_config["TenantScope"].to_s.strip
          scope unless scope.empty?
        end
      end
    end
  end
end
