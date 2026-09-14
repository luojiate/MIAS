import { Root } from '@radix-ui/react-label'
import type { ComponentPropsWithoutRef } from 'react'
import { cn } from '@/lib/utils'

function Label({ className, ...props }: ComponentPropsWithoutRef<typeof Root>) {
  return (
    <Root
      className={cn('text-sm font-medium leading-none text-zinc-700 peer-disabled:cursor-not-allowed peer-disabled:opacity-70', className)}
      {...props}
    />
  )
}

export { Label }
