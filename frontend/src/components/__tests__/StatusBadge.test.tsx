// src/components/__tests__/StatusBadge.test.tsx
/**
 * StatusBadge 组件测试
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test/utils';
import { StatusBadge } from '../StatusBadge';

describe('StatusBadge', () => {
  describe('workflow status', () => {
    it('should render pending status correctly', () => {
      render(<StatusBadge status="pending" type="workflow" />);
      expect(screen.getByText('待处理')).toBeInTheDocument();
    });

    it('should render running status correctly', () => {
      render(<StatusBadge status="running" type="workflow" />);
      expect(screen.getByText('执行中')).toBeInTheDocument();
    });

    it('should render completed status correctly', () => {
      render(<StatusBadge status="completed" type="workflow" />);
      expect(screen.getByText('已完成')).toBeInTheDocument();
    });

    it('should render failed status correctly', () => {
      render(<StatusBadge status="failed" type="workflow" />);
      expect(screen.getByText('失败')).toBeInTheDocument();
    });

    it('should render paused_approval status correctly', () => {
      render(<StatusBadge status="paused_approval" type="workflow" />);
      expect(screen.getByText('等待审批')).toBeInTheDocument();
    });
  });

  describe('health status', () => {
    it('should render healthy status correctly', () => {
      render(<StatusBadge status="healthy" type="health" />);
      expect(screen.getByText('健康')).toBeInTheDocument();
    });

    it('should render degraded status correctly', () => {
      render(<StatusBadge status="degraded" type="health" />);
      expect(screen.getByText('降级')).toBeInTheDocument();
    });

    it('should render unhealthy status correctly', () => {
      render(<StatusBadge status="unhealthy" type="health" />);
      expect(screen.getByText('不健康')).toBeInTheDocument();
    });
  });

  describe('status colors', () => {
    it('should use correct color for pending status', () => {
      const { container } = render(<StatusBadge status="pending" type="workflow" />);
      const badge = container.querySelector('.ant-tag');
      expect(badge).toHaveClass('ant-tag-default');
    });

    it('should use correct color for running status', () => {
      const { container } = render(<StatusBadge status="running" type="workflow" />);
      const badge = container.querySelector('.ant-tag');
      expect(badge).toHaveClass('ant-tag-processing');
    });

    it('should use correct color for completed status', () => {
      const { container } = render(<StatusBadge status="completed" type="workflow" />);
      const badge = container.querySelector('.ant-tag');
      expect(badge).toHaveClass('ant-tag-success');
    });

    it('should use correct color for failed status', () => {
      const { container } = render(<StatusBadge status="failed" type="workflow" />);
      const badge = container.querySelector('.ant-tag');
      expect(badge).toHaveClass('ant-tag-error');
    });
  });
});
