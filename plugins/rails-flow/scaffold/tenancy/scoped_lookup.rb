# frozen_string_literal: true

module RuboCop
  module Cop
    module Tenancy
      # Flags a lookup on a tenant-owned model's CONSTANT — `Document.find(params[:id])` — which
      # reads across every tenant, and points at the tenant-scoped association instead:
      # `Current.organization.documents.find(params[:id])`.
      #
      #   Tenancy/ScopedLookup:
      #     Enabled: true
      #     SafeAutoCorrect: false          # `rubocop -a` reports it; only `-A` rewrites it
      #     Include: [app/controllers/**/*.rb]
      #     Exclude: [app/controllers/admin/**/*.rb]
      #     TenantScope: Current.organization
      #     TenantOwnedModels:
      #       Document: documents
      #       Billing::Invoice: invoices
      class ScopedLookup < Base
        extend AutoCorrector

        MSG = "`%<model>s.%<method>s` reads across every tenant. Scope it: `%<scoped>s.%<method>s`."

        # Fixed, not configurable: RuboCop does not validate a local cop's keys, so a mistyped
        # method list would silently check nothing.
        RESTRICT_ON_SEND = %i[find find_by find_by! find_sole_by where all].freeze

        def on_send(node)
          receiver = node.receiver
          return unless receiver&.const_type?

          model = receiver.const_name
          association = tenant_owned_models[model]
          return unless association

          scoped = [tenant_scope, association].compact.join(".")
          message = format(MSG, model: model, method: node.method_name, scoped: scoped)
          add_offense(node, message: message) do |corrector|
            corrector.replace(receiver, scoped) if tenant_scope
          end
        end

        private

        def tenant_owned_models
          cop_config.fetch("TenantOwnedModels", {}).to_h { |model, assoc| [model.to_s.delete_prefix("::"), assoc.to_s] }
        end

        def tenant_scope
          cop_config["TenantScope"]
        end
      end
    end
  end
end
